"""产品帮助检索工具：给 Agent 用，查的是内置帮助知识库。"""
from __future__ import annotations

from typing import Any

from .. import help as help_kb
from .web_search import ToolError


def run(query: str, top_k: int = 4) -> dict:
    q = (query or "").strip()
    if not q:
        raise ToolError("query 不能为空")
    try:
        items: list[dict[str, Any]] = help_kb.search(q, top_k)
    except Exception as e:  # noqa: BLE001
        raise ToolError(f"帮助知识库读取失败：{e}") from e
    if not items:
        raise ToolError("帮助知识库里没有相关内容")
    return {"items": items}
