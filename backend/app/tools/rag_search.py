"""本地 RAG 检索工具：包一层 LanceDB 向量检索，返回可直接引用的分块。"""
from __future__ import annotations

from typing import Any

from ..vector import lancedb_store as vs
from .web_search import ToolError


def run(query: str, top_k: int = 5, doc_scope: str = "", workspace: str = "") -> dict:
    q = (query or "").strip()
    if not q:
        raise ToolError("query 不能为空")
    k = max(1, min(int(top_k or 5), 8))
    try:
        items: list[dict[str, Any]] = vs.search_documents(q, k, doc_scope or "", workspace or "")
    except Exception as e:  # noqa: BLE001  向量库/模型没就绪时给出可读原因
        raise ToolError(f"本地检索不可用：{e}") from e
    if not items:
        raise ToolError("知识库里没有检索到相关内容")
    return {"items": items}
