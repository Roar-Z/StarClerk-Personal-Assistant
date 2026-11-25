"""chat 分组：会话 CRUD + 一次 ReAct 对话（同步图放到线程池，避免堵事件循环）。"""
from __future__ import annotations

import asyncio
from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from ..agent import graph
from ..db import models as meta
from .deps import failure

router = APIRouter(prefix="/chat", tags=["chat"])


class ChatIn(BaseModel):
    session_id: str | None = None
    message: str = Field(min_length=1, max_length=8000)
    use_rag: bool = True
    doc_scope: str = ""


class ChatOut(BaseModel):
    session_id: str
    answer: str
    contexts: list[dict[str, Any]] = []
    memories: list[str] = []
    steps: list[dict[str, Any]] = []
    usage: dict[str, int] = {}
    should_notify: bool = False
    level: str = "info"


class SessionIn(BaseModel):
    title: str = Field(default="新对话", max_length=60)


@router.post("", response_model=ChatOut, summary="对话（检索 + 记忆 + 工具）")
async def chat(body: ChatIn):
    text = body.message.strip()
    if not text:
        raise HTTPException(400, "消息不能为空")
    sid = body.session_id or meta.create_session(text[:60])["id"]
    try:
        res = await asyncio.to_thread(graph.run_chat, sid, text, body.use_rag, body.doc_scope)
    except Exception as e:  # noqa: BLE001
        raise failure("chat", e) from e
    res.pop("notice", None)  # 对话不推托盘，只保留标记
    return res


# ---------------- 会话 ----------------
@router.get("/sessions", summary="会话列表")
def list_sessions(limit: int = 50):
    return meta.list_sessions(max(1, min(limit, 200)))


@router.post("/sessions", summary="新建会话")
def create_session(body: SessionIn):
    return meta.create_session(body.title or "新对话")


@router.get("/sessions/{sid}/messages", summary="会话消息")
def messages(sid: str):
    return meta.rows("SELECT * FROM messages WHERE session_id=? ORDER BY created_at", (sid,))


@router.delete("/sessions/{sid}", summary="删除会话")
def remove_session(sid: str):
    meta.delete_session(sid)
    return {"ok": True}
