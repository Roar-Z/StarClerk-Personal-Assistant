"""chat 分组：会话 CRUD + 一次 ReAct 对话（同步图放到线程池，避免堵事件循环）。

游客和登录用户的区别只在这里处理：游客会话存内存，不落库，导出接口也被中间件挡住。
"""
from __future__ import annotations

import asyncio
import time
from typing import Any

from fastapi import APIRouter, HTTPException
from fastapi.responses import Response
from pydantic import BaseModel, Field

from .. import license, sessions
from ..access import require
from ..agent import graph
from .deps import failure

router = APIRouter(prefix="/chat", tags=["chat"])


class ChatIn(BaseModel):
    session_id: str | None = None
    message: str = Field(min_length=1, max_length=8000)
    use_rag: bool = True
    doc_scope: str = ""
    workspace: str = ""


class ChatOut(BaseModel):
    session_id: str
    answer: str
    contexts: list[dict[str, Any]] = []
    memories: list[str] = []
    steps: list[dict[str, Any]] = []
    usage: dict[str, int] = {}
    should_notify: bool = False
    level: str = "info"
    tier: str = "free"


class SessionIn(BaseModel):
    title: str = Field(default="新对话", max_length=60)


@router.post("", response_model=ChatOut, summary="对话（检索 + 记忆 + 工具）")
async def chat(body: ChatIn):
    text = body.message.strip()
    if not text:
        raise HTTPException(400, "消息不能为空")
    guest = license.is_guest()
    sid = body.session_id or sessions.create(text[:60])["id"]
    try:
        if guest:
            # 游客：无 RAG、无长期记忆、历史从内存拿，回答完再写回内存
            hist = sessions.history(sid, 10)
            res = await asyncio.to_thread(graph.run_chat, sid, text, False, "", False, hist)
            sessions.append(sid, "user", text)
            sessions.append(sid, "assistant", res["answer"])
            if not hist:
                sessions.touch_title(sid, text[:60])
        else:
            res = await asyncio.to_thread(
                graph.run_chat, sid, text, body.use_rag, body.doc_scope, True, None, body.workspace
            )
    except Exception as e:  # noqa: BLE001
        raise failure("chat", e) from e
    res.pop("notice", None)  # 对话不推托盘，只保留标记
    res["session_id"] = sid
    res["tier"] = license.tier()
    return res


# ---------------- 会话 ----------------
@router.get("/sessions", summary="会话列表（免费版起）")
def list_sessions(limit: int = 50):
    return sessions.list_all(max(1, min(limit, 200)))


@router.post("/sessions", summary="新建会话（免费版起）")
def create_session(body: SessionIn):
    return sessions.create(body.title or "新对话")


@router.get("/sessions/{sid}/messages", summary="会话消息")
def messages(sid: str):
    return sessions.messages(sid)


@router.delete("/sessions/{sid}", summary="删除会话")
def remove_session(sid: str):
    sessions.drop(sid)
    return {"ok": True}


@router.get("/export", summary="导出会话为 Markdown（免费版起）")
def export_session(sid: str):
    require("export")
    body = sessions.all_messages_text(sid)
    if not body:
        raise HTTPException(404, "这个会话还没有内容")
    md = f"# {sessions.title(sid)}\n\n> 导出于 {time.strftime('%Y-%m-%d %H:%M')}\n\n{body}\n"
    name = f"chat-{sid[:8]}.md"
    return Response(
        content=md,
        media_type="text/markdown; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{name}"'},
    )
