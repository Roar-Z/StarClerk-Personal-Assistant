"""四个节点：记忆召回 → 计划（决定调工具或直接回答）→ 工具调用 → 总结判断。

刻意保持单层 ReAct：没有子图、没有并行工具、没有反思子 Agent，每次最多调 1 个工具。
"""
from __future__ import annotations

import logging
from typing import Any

from ..config import settings
from ..llm import client
from ..tools import registry
from . import memory as mem_store
from . import prompts
from .state import AgentState, merge_usage

log = logging.getLogger("agent")


# ---------------------------------------------------------------- 记忆召回
def node_recall(state: AgentState) -> AgentState:
    """每轮思考前都查一次 LanceDB：迭代时用「问题 + 上一条观测」做查询，能带回新线索。"""
    if not state.get("allow_memory", True):
        return {"memories": [], "recalled_for": ""}
    query = _focus_query(state)
    try:
        found = mem_store.recall(query, settings.agent_memory_top_k)
    except Exception as e:  # noqa: BLE001  记忆不可用不影响主流程
        log.warning("记忆召回失败：%s", e)
        found = []
    return {"memories": _dedupe(found)[: settings.agent_memory_top_k], "recalled_for": query}


def _focus_query(state: AgentState) -> str:
    obs = state.get("observations") or []
    if not obs:
        return state["query"]
    return f"{state['query']} {str(obs[-1].get('summary', ''))[:80]}".strip()


# ---------------------------------------------------------------- 计划节点
def node_plan(state: AgentState) -> AgentState:
    use_rag = state.get("use_rag", True)
    allow_web = state.get("allow_web", True)
    allow_todo = bool(state.get("allow_todo", False))
    tools = registry.schemas(use_rag=use_rag, allow_web=allow_web, allow_todo=allow_todo)
    iteration = int(state.get("iterations", 0)) + 1

    # 产品使用类问题不靠模型自觉，命中意图就先查内置帮助。查过一次就不再强制，避免死循环。
    seen = {o.get("tool") for o in state.get("observations") or []}
    if state.get("mode") == "chat":
        if "help_search" not in seen and prompts.is_help_intent(state.get("query", "")):
            return {
                "iterations": iteration,
                "pending_calls": [{"name": "help_search", "arguments": {"query": state["query"]}}],
                "draft": "",
                "steps": [{"index": iteration, "kind": "think", "content": "使用类问题，先查内置帮助"}],
            }
        if "todo_add" not in seen and allow_todo and prompts.is_todo_intent(state.get("query", "")):
            return {
                "iterations": iteration,
                "pending_calls": [{"name": "todo_add", "arguments": {"text": state["query"]}}],
                "draft": "",
                "steps": [{"index": iteration, "kind": "think", "content": "待办类问题，直接写进清单"}],
            }

    messages: list[dict[str, Any]] = [{"role": "system", "content": _system_prompt(state)}]
    messages += state.get("history", [])[-6:]
    messages.append({"role": "user", "content": state["query"]})

    try:
        res = client.complete(
            messages, tools=tools or None, temperature=0.2, scope=state.get("mode", "chat")
        )
    except client.LLMError as e:
        log.warning("计划节点模型失败：%s", e)
        return {
            "iterations": iteration,
            "error": f"模型不可用：{e}",
            "pending_calls": [],
            "draft": "",
            "steps": [{"index": iteration, "kind": "think", "content": "模型调用失败"}],
        }

    allowed = {t["function"]["name"] for t in tools}
    calls = [c for c in res.tool_calls if c["name"] in allowed][:1]
    step_text = res.content[:200] if calls else f"直接回答（{res.latency_ms}ms）"
    return {
        "iterations": iteration,
        "pending_calls": calls,
        "draft": "" if calls else res.content,
        "steps": [{"index": iteration, "kind": "think", "content": step_text}],
        "usage": merge_usage(state.get("usage"), res.usage),
    }


def _system_prompt(state: AgentState) -> str:
    rules = prompts.PATROL_RULES if state.get("mode") == "patrol" else prompts.PLAN_RULES
    parts = [prompts.ROLE, rules]
    mem = prompts.render_memories(state.get("memories") or [])
    if mem:
        parts.append(mem)
    obs = prompts.render_observations(state.get("observations") or [])
    if obs:
        parts.append(obs)
    if state.get("doc_scope"):
        parts.append(f"【检索范围】仅限 doc_id: {state['doc_scope']}")
    return "\n\n".join(parts)


# ---------------------------------------------------------------- 工具调用节点
def node_act(state: AgentState) -> AgentState:
    calls = state.get("pending_calls") or []
    if not calls:
        return {}

    observations: list[dict[str, Any]] = []
    contexts = list(state.get("contexts") or [])
    steps = []
    for call in calls[:1]:
        result = registry.execute(
            call["name"],
            call.get("arguments"),
            state.get("doc_scope", ""),
            state.get("workspace", ""),
        )
        observations.append(
            {
                "tool": result["tool"],
                "arguments": result["arguments"],
                "ok": result["ok"],
                "summary": result["summary"],
            }
        )
        if result["tool"] in ("rag_search", "help_search", "todo_add"):
            contexts = _merge_contexts(contexts, result.get("data") or [])
        steps.append(
            {
                "index": int(state.get("iterations", 1)),
                "kind": "tool",
                "content": f"{result['tool']}({_brief(result['arguments'])}) → {'成功' if result['ok'] else '失败'}",
            }
        )
    return {"pending_calls": [], "observations": observations, "contexts": contexts, "steps": steps}


# ---------------------------------------------------------------- 总结判断节点
def node_judge(state: AgentState) -> AgentState:
    """判断信息是否足够：能定稿就定稿，明确缺信息且还有步数就回计划节点再检索一次。"""
    if state.get("error"):
        return {
            "answer": state["error"],
            "should_notify": False,
            "notify_level": "info",
            "need_more": False,
            "steps": [{"index": int(state.get("iterations", 1)), "kind": "finish", "content": "模型不可用"}],
        }

    # 写待办是确定动作，写进去就直接回执，不再让模型多问一句“要加吗”
    last = (state.get("observations") or [])[-1] if state.get("observations") else None
    if last and last.get("tool") == "todo_add" and last.get("ok"):
        answer = str(last.get("summary") or "已加入待办")
        return {
            "answer": answer,
            "need_more": False,
            "usage": state.get("usage") or {},
            "steps": [{"index": int(state.get("iterations", 1)), "kind": "finish", "content": answer[:120]}],
        }

    draft = (state.get("draft") or "").strip()
    steps_left = int(state.get("iterations", 0)) < int(state.get("max_steps", settings.agent_max_steps))
    retries = int(state.get("retries", 0))
    # 只回退补检索一次：既给模型补救机会，也避免“信息不足”来回打转烧 token
    if draft and steps_left and retries < 1 and _insufficient(draft):
        return {
            "draft": "",
            "answer": "",
            "retries": retries + 1,
            "need_more": True,
            "steps": [{"index": int(state.get("iterations", 1)), "kind": "think", "content": "判断：信息不足，继续检索"}],
        }

    usage = state.get("usage")
    if draft:
        answer = draft
    else:
        answer, extra = _summarize(state)
        usage = merge_usage(usage, extra)

    signal = _patrol_signal(answer) if state.get("mode") == "patrol" else {"should_notify": False, "notify_level": "info"}
    return {
        "answer": answer,
        "need_more": False,
        "usage": usage,
        "steps": [{"index": int(state.get("iterations", 1)), "kind": "finish", "content": answer[:120]}],
        **signal,
    }


def _insufficient(text: str) -> bool:
    return any(k in text for k in prompts.INSUFFICIENT)


def _patrol_signal(answer: str) -> dict[str, Any]:
    """巡检提醒信号：只说“无异常”则静默；含风险词则升级为 warn。"""
    rest = answer
    for phrase in prompts.NO_ISSUE:
        rest = rest.replace(phrase, "")
    has_risk = any(k in rest for k in prompts.RISK_WORDS)
    no_issue = any(k in answer for k in prompts.NO_ISSUE)
    return {
        "should_notify": has_risk or not no_issue,
        "notify_level": "warn" if has_risk else "info",
    }


def _summarize(state: AgentState) -> tuple[str, dict[str, int]]:
    """没有直接答复（步数用尽/只调了工具）时，把观测压成最终答复。"""
    obs = prompts.render_observations(state.get("observations") or [])
    if not obs:
        fallback = "无异常" if state.get("mode") == "patrol" else "没有检索到可用信息，可以补充资料后再试。"
        return fallback, {}
    messages = [
        {"role": "system", "content": prompts.SUMMARIZE + _mode_tail(state)},
        {"role": "user", "content": f"用户问题：{state['query']}\n\n{obs}"},
    ]
    try:
        res = client.complete(messages, temperature=0.2, scope=state.get("mode", "chat"))
    except client.LLMError as e:
        log.warning("总结节点模型失败：%s", e)
        return obs, {}
    return res.content or obs, res.usage


def _mode_tail(state: AgentState) -> str:
    if state.get("mode") == "patrol":
        return "\n巡检场景：只保留需要关注的点；没有异常时只回复：无异常。"
    return ""


# ---------------------------------------------------------------- 小工具
def _dedupe(items: list[str]) -> list[str]:
    seen: set[str] = set()
    out = []
    for it in items:
        key = it.strip()
        if key and key not in seen:
            seen.add(key)
            out.append(key)
    return out


def _merge_contexts(current: list[dict], incoming: list[dict]) -> list[dict]:
    seen = {(c.get("doc_id"), str(c.get("text"))[:40]) for c in current}
    for item in incoming:
        key = (item.get("doc_id"), str(item.get("text"))[:40])
        if key not in seen:
            seen.add(key)
            current.append(item)
    return current[-8:]


def _brief(arguments: dict) -> str:
    text = ", ".join(f"{k}={v}" for k, v in list(arguments.items())[:2])
    return text[:80]
