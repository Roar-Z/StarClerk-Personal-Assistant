"""工具注册表：schema 直接喂给 OpenAI 兼容的 tool calling，handler 统一返回 text/data。

刻意只保留两个工具（网页搜索、本地 RAG），不提供 ComputerUse / 代码执行等能力。
"""
from __future__ import annotations

import json
from typing import Any, Callable

from . import rag_search, web_search

MAX_SUMMARY = 1500

_SPECS: dict[str, dict[str, Any]] = {
    "web_search": {
        "type": "function",
        "function": {
            "name": "web_search",
            "description": "搜索公网信息，适合时效性内容或本地资料没有的事实。返回标题、链接、摘要。",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "具体检索词，不要照抄整句问题"},
                    "top_k": {"type": "integer", "description": "返回条数，默认 5，最多 8"},
                },
                "required": ["query"],
            },
        },
    },
    "rag_search": {
        "type": "function",
        "function": {
            "name": "rag_search",
            "description": "检索用户本地知识库文档（个人资料、项目文档、历史记录），返回可引用的原文分块。",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "检索词或关键短语"},
                    "top_k": {"type": "integer", "description": "返回分块数，默认 5，最多 8"},
                },
                "required": ["query"],
            },
        },
    },
}

_HANDLERS: dict[str, Callable[..., dict]] = {
    "web_search": web_search.run,
    "rag_search": rag_search.run,
}


def schemas(use_rag: bool = True, allow_web: bool = True) -> list[dict[str, Any]]:
    """按本次请求允许的工具裁剪 schema，模型不会看到被禁用的工具。"""
    names = []
    if allow_web:
        names.append("web_search")
    if use_rag:
        names.append("rag_search")
    return [_SPECS[n] for n in names]


def execute(
    name: str,
    arguments: dict[str, Any] | str | None,
    doc_scope: str = "",
    workspace: str = "",
) -> dict[str, Any]:
    """执行一次工具调用；任何异常都收敛成 ok=False 的观测，保证图能继续跑。"""
    args = _parse_args(arguments)
    handler = _HANDLERS.get(name)
    if handler is None:
        return _fail(name, args, f"未知工具：{name}")
    if name == "rag_search":
        args.setdefault("doc_scope", doc_scope)
        if workspace:
            args.setdefault("workspace", workspace)
    try:
        data = handler(**args)
    except Exception as e:  # noqa: BLE001  工具失败不应中断对话
        return _fail(name, args, str(e)[:300])
    items = data.get("items", [])
    return {
        "ok": True,
        "tool": name,
        "arguments": args,
        "summary": _summarize(name, items)[:MAX_SUMMARY],
        "data": items,
    }


def _parse_args(raw: dict[str, Any] | str | None) -> dict[str, Any]:
    if isinstance(raw, dict):
        return dict(raw)
    if isinstance(raw, str) and raw.strip():
        try:
            parsed = json.loads(raw)
            return parsed if isinstance(parsed, dict) else {}
        except json.JSONDecodeError:
            return {"query": raw[:200]}
    return {}


def _summarize(name: str, items: list[dict[str, Any]]) -> str:
    if not items:
        return "没有结果"
    lines: list[str] = []
    for i, it in enumerate(items, 1):
        if name == "web_search":
            lines.append(f"{i}. {it.get('title', '')} — {it.get('url', '')}\n   {it.get('snippet', '')}")
        else:
            lines.append(f"{i}. [{it.get('source', '资料')}] {it.get('text', '')}")
    return "\n".join(lines)


def _fail(name: str, args: dict[str, Any], reason: str) -> dict[str, Any]:
    return {
        "ok": False,
        "tool": name,
        "arguments": args,
        "summary": f"{name} 调用失败：{reason}",
        "data": [],
    }
