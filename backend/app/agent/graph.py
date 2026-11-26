"""LangGraph 装配与对外入口：FastAPI / 调度器只管调 run_chat、run_patrol。

图形状（一条主线，最多 1 个工具/轮）：

    START → recall → plan ─┬─(有工具调用)→ act ─┬─(还有步数)→ recall
                            │                    └─(步数用尽)→ judge
                            └─(无工具调用)→ judge ─┬─(判断信息不足)→ recall
                                                   └─(定稿)→ END

recall 放在环上，是为了满足「每次思考前都从 LanceDB 召回长期记忆」。
"""
from __future__ import annotations

import logging
import threading
from typing import Any

from langgraph.graph import END, START, StateGraph

from ..config import settings
from ..db import models as meta
from . import memory, nodes
from .state import AgentState

log = logging.getLogger("graph")


# ---------------------------------------------------------------- 路由
def _after_plan(state: AgentState) -> str:
    return "act" if state.get("pending_calls") else "judge"


def _after_act(state: AgentState) -> str:
    last = (state.get("observations") or [])[-1] if state.get("observations") else None
    if last and last.get("tool") == "todo_add" and last.get("ok"):
        return "judge"  # 已经写进去了，直接出回执，不再烧一次模型
    if int(state.get("iterations", 0)) < int(state.get("max_steps", settings.agent_max_steps)):
        return "recall"
    return "judge"


def _after_judge(state: AgentState) -> str:
    return "recall" if state.get("need_more") else "end"


# ---------------------------------------------------------------- 编译入口
def _build():
    g = StateGraph(AgentState)
    g.add_node("recall", nodes.node_recall)
    g.add_node("plan", nodes.node_plan)
    g.add_node("act", nodes.node_act)
    g.add_node("judge", nodes.node_judge)

    g.add_edge(START, "recall")
    g.add_edge("recall", "plan")
    g.add_conditional_edges("plan", _after_plan, {"act": "act", "judge": "judge"})
    g.add_conditional_edges("act", _after_act, {"recall": "recall", "judge": "judge"})
    g.add_conditional_edges("judge", _after_judge, {"recall": "recall", "end": END})
    return g.compile()


_graph = None


def get_graph():
    """进程内单例；编译有开销，只在首次调用时构建。"""
    global _graph
    if _graph is None:
        _graph = _build()
        log.info("Agent 图已编译")
    return _graph


def _invoke(payload: dict[str, Any]) -> AgentState:
    steps = int(payload.get("max_steps") or settings.agent_max_steps)
    # 每轮最多 3 个节点，留足余量避免 RecursionLimit 误报
    return get_graph().invoke(payload, config={"recursion_limit": 3 * steps + 8})


# ---------------------------------------------------------------- 对话
def run_chat(
    session_id: str,
    query: str,
    use_rag: bool = True,
    doc_scope: str = "",
    save: bool = True,
    hist: list[dict[str, str]] | None = None,
    workspace: str = "",
) -> dict[str, Any]:
    """同步执行一次问答；会话读写与记忆沉淀都在这里，API 层保持很薄。

    未登录模式传 save=False + hist（API 层从内存里取上一轮），
    顺便把 RAG 和长期记忆都关掉——这是三档权限里未登录的边界。
    """
    from .. import license

    guest = license.is_guest()
    if save:
        meta.add_message(session_id, "user", query)
    history = hist if hist is not None else (meta.history(session_id, 10) if save else [])
    if save and history and history[-1].get("content") == query:
        history = history[:-1]  # 刚写进去的这条别重复喂给模型
    allow_memory = not guest
    use_rag = bool(use_rag) and not guest

    state = _invoke(
        {
            "query": query,
            "mode": "chat",
            "history": history[-10:],
            "use_rag": use_rag,
            "allow_memory": allow_memory,
            "allow_todo": not guest,
            "allow_web": settings.web_search_enabled,
            "doc_scope": doc_scope,
            "workspace": workspace,
            "max_steps": settings.agent_max_steps,
            "persist_memory": save and allow_memory,
        }
    )
    answer = state.get("answer") or "（没有生成回复）"
    if state.get("error"):
        # 模型不可用时不写脏数据、不重命名会话，让 API 层回 502
        raise RuntimeError(state["error"])

    if save:
        meta.add_message(session_id, "assistant", answer)
        if len(history) <= 1:
            meta.rename_session(session_id, query)
        if allow_memory:
            threading.Thread(
                target=memory.extract_and_store, args=(query, answer), daemon=True
            ).start()

    return {
        "answer": answer,
        "session_id": session_id,
        "contexts": state.get("contexts", []),
        "memories": state.get("memories", []),
        "steps": state.get("steps", []),
        "usage": state.get("usage", {}),
        # 对话不主动提醒，但统一带上标记，前端/托盘可无脑读同一份结构
        "should_notify": False,
        "level": "info",
        "notice": None,
    }


# ---------------------------------------------------------------- 巡检
def run_patrol(name: str, prompt: str, doc_scope: str = "", workspace: str = "") -> dict[str, Any]:
    """定时巡检：不落会话、不写记忆，只回结论 + 提醒信号（托盘/SSE 消费）。"""
    state = _invoke(
        {
            "query": prompt,
            "mode": "patrol",
            "history": [],
            "use_rag": True,
            "allow_memory": False,  # 巡检只要资料，不用带个人记忆
            "allow_web": settings.patrol_allow_web,
            "doc_scope": doc_scope,
            "workspace": workspace,
            "max_steps": 2,
            "persist_memory": False,
        }
    )
    answer = (state.get("answer") or "").strip() or "无异常"
    ok = not bool(state.get("error"))
    should_notify = bool(state.get("should_notify")) and ok
    level = state.get("notify_level", "info")
    return {
        "name": name,
        "ok": ok,
        "result": answer,
        "should_notify": should_notify,
        "level": level,
        # 提醒标记：托盘 / SSE 直接消费，无需再判文案
        "notice": {"title": f"巡检提醒 · {name}", "body": answer[:180], "level": level}
        if should_notify
        else None,
        "contexts": state.get("contexts", []),
        "usage": state.get("usage", {}),
    }
