"""笔记：Pro 的。存标题、正文、分类、标签，就这几样。

检索没单独建索引，标题和正文直接 LIKE；文档那一半交给 LanceDB 的向量检索，
失败就退回按文件名对一下，别让整页报错。
"""
from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from ..access import check_limit
from ..db import models
from ..vector import lancedb_store as vs

router = APIRouter(prefix="/notes", tags=["notes"])


class NoteIn(BaseModel):
    title: str = Field(default="无标题", max_length=120)
    body: str = ""
    category: str = ""
    tags: str = ""


class NotePatch(BaseModel):
    title: str | None = None
    body: str | None = None
    category: str | None = None
    tags: str | None = None
    pinned: int | None = None


@router.get("", summary="笔记列表")
def list_notes(q: str = "", category: str = "", tag: str = "", limit: int = 200):
    items = models.find_notes(q.strip(), category, tag, max(1, min(limit, 500)))
    return {
        "items": items,
        "total": models.count_notes(),
        "categories": models.note_categories(),
    }


@router.get("/search", summary="笔记 + 文档一起搜")
def search_all(q: str, limit: int = 20):
    """先查笔记，再问一遍向量库。向量库那边挂了就当没查到文档。"""
    text = q.strip()
    if not text:
        raise HTTPException(400, "搜索词不能为空")
    notes = models.find_notes(text, limit=limit)
    docs: list[dict] = []
    try:
        docs = vs.search_documents(text, limit)
    except Exception:  # noqa: BLE001
        docs = [d for d in vs.list_documents() if text.lower() in (d.get("source") or "").lower()][:limit]
    return {"q": text, "notes": notes, "docs": docs}


@router.post("", summary="新建笔记")
def add_note(body: NoteIn):
    check_limit("notes", models.count_notes())
    title = body.title.strip() or "无标题"
    return models.create_note(title, body.body, body.category.strip(), body.tags.strip())


@router.get("/{nid}", summary="笔记详情")
def get_note(nid: str):
    note = models.get_note(nid)
    if note is None:
        raise HTTPException(404, "这条笔记不存在")
    return note


@router.put("/{nid}", summary="保存笔记")
def save_note(nid: str, body: NotePatch):
    if models.get_note(nid) is None:
        raise HTTPException(404, "这条笔记不存在")
    note = models.update_note(nid, **body.model_dump(exclude_unset=True))
    return note


@router.delete("/{nid}", summary="删除笔记")
def remove_note(nid: str):
    models.delete_note(nid)
    return {"ok": True}
