"""对话：一问一答、流式、图片认字、会话管理、导出。

普通问答走 Agent 图，能检索、能调工具、会顺手写记忆；
流式那条路图跑不动，就自己拼上下文直接问模型，速度快点但没有工具。
未登录的会话只放内存，导出和列表都被中间件按档位挡住。
"""
from __future__ import annotations

import asyncio
import json
import time
from typing import Any, Iterator

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import Response, StreamingResponse
from pydantic import BaseModel, Field

from .. import license, quota, sessions, ocr
from ..access import require
from ..agent import graph
from ..db import models
from ..export import docx_bytes
from ..llm import client as llm
from ..vector import lancedb_store as vs
from .deps import failure

router = APIRouter(prefix="/chat", tags=["chat"])

SYSTEM = (
    "你是 StarClerk，运行在用户自己电脑上的桌面助手。回答尽量具体，别绕圈子，"
    "不确定就说不确定。下面的资料片段如果和问题有关就用上，无关就别硬塞。"
)


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
    quota: dict[str, Any] | None = None


class SessionIn(BaseModel):
    title: str = Field(default="新对话", max_length=60)


class OcrIn(BaseModel):
    image: str = Field(min_length=32)
    hint: str = ""


# 未登录的上下文只放在进程里，关掉程序就没了，正好对上“对话不保存”这句承诺
_guest_hist: dict[str, list[dict[str, str]]] = {}
_guest_seq = 0


def _guest_sid() -> str:
    global _guest_seq
    _guest_seq += 1
    return f"g{int(time.time())}-{_guest_seq}"


def _guest_remember(sid: str, question: str, answer: str) -> None:
    box = _guest_hist.setdefault(sid, [])
    box.append({"role": "user", "content": question})
    box.append({"role": "assistant", "content": answer})
    del box[:-20]
    if len(_guest_hist) > 100:  # 开一整天也别一直涨
        _guest_hist.pop(next(iter(_guest_hist)))


def _ctx_block(hits: list[dict[str, Any]]) -> str:
    if not hits:
        return ""
    parts = []
    for i, h in enumerate(hits, 1):
        parts.append(f"[{i}] {h.get('source', '文档')}\n{str(h.get('text', ''))[:1200]}")
    return "\n\n".join(parts)


def _prompt(text: str, hist: list[dict[str, str]], hits: list[dict[str, Any]]) -> list[dict[str, Any]]:
    msgs: list[dict[str, Any]] = [{"role": "system", "content": SYSTEM}]
    block = _ctx_block(hits)
    if block:
        msgs.append({"role": "system", "content": "资料片段：\n" + block})
    for h in hist[-8:]:
        msgs.append({"role": h.get("role") or "user", "content": h.get("content") or ""})
    msgs.append({"role": "user", "content": text})
    return msgs


@router.post("", response_model=ChatOut, summary="对话（检索 + 记忆 + 工具）")
async def chat(body: ChatIn):
    text = body.message.strip()
    if not text:
        raise HTTPException(400, "消息不能为空")
    guest = license.is_guest()
    if guest:
        quota.check()
    sid = body.session_id or (_guest_sid() if guest else sessions.create(text[:60])["id"])
    try:
        if guest:
            hist = list(_guest_hist.get(sid, []))
            res = await asyncio.to_thread(graph.run_chat, sid, text, False, "", False, hist)
            _guest_remember(sid, text, res["answer"])
            quota.hit()
        else:
            res = await asyncio.to_thread(
                graph.run_chat, sid, text, body.use_rag, body.doc_scope, True, None, body.workspace
            )
    except Exception as e:  # noqa: BLE001
        raise failure("chat", e) from e
    res.pop("notice", None)
    res["session_id"] = sid
    res["tier"] = license.tier()
    if guest:
        res["quota"] = quota.snapshot()
    return res


@router.post("/stream", summary="流式对话")
def chat_stream(body: ChatIn):
    """SSE。先把检索和历史准备好，再一段段吐字，结束后落库。"""
    text = body.message.strip()
    if not text:
        raise HTTPException(400, "消息不能为空")
    guest = license.is_guest()
    if guest:
        quota.check()
    sid = body.session_id or (_guest_sid() if guest else sessions.create(text[:60])["id"])

    def gen() -> Iterator[str]:
        def frame(obj: dict[str, Any]) -> str:
            return "data: " + json.dumps(obj, ensure_ascii=False) + "\n\n"

        yield frame({"type": "meta", "session_id": sid, "tier": license.tier()})
        hits: list[dict[str, Any]] = []
        if body.use_rag and not guest:
            try:
                hits = vs.search_documents(text, 4)
            except Exception:  # noqa: BLE001  检索挂了也别影响回答
                hits = []
        hist = list(_guest_hist.get(sid, [])) if guest else sessions.history(sid, 10)
        parts: list[str] = []
        try:
            for piece in llm.stream_text(_prompt(text, hist, hits), session_id=sid):
                parts.append(piece)
                yield frame({"type": "delta", "text": piece})
        except Exception as e:  # noqa: BLE001
            yield frame({"type": "error", "message": str(e)[:300]})
            return

        answer = "".join(parts).strip()
        if not answer:
            yield frame({"type": "error", "message": "模型没吐出内容，换个模型试试"})
            return
        if guest:
            _guest_remember(sid, text, answer)
        else:
            sessions.append(sid, "user", text)
            sessions.append(sid, "assistant", answer)
            if not hist:
                sessions.touch_title(sid, text[:60])
        done: dict[str, Any] = {
            "type": "done",
            "answer": answer,
            "contexts": [{"source": h.get("source", ""), "text": str(h.get("text", ""))[:200]} for h in hits],
            "tier": license.tier(),
        }
        if guest:
            quota.hit()
            done["quota"] = quota.snapshot()
        yield frame(done)

    return StreamingResponse(
        gen(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@router.post("/ocr", summary="图片转文字（本地 OCR）")
def ocr_image(body: OcrIn):
    """兼容老前端；实际识别走 /api/ocr/local，不联网也不占模型额度。"""
    img = body.image.strip()
    if not img.startswith("data:image/"):
        raise HTTPException(400, "图片格式不对，要 data:image/... 开头的 base64")
    if len(img) > 8 * 1024 * 1024:
        raise HTTPException(400, "图片太大了，压缩一下再传")
    try:
        hit = ocr.recognize(img)
    except ValueError as e:
        raise HTTPException(400, str(e)) from e
    except Exception as e:  # noqa: BLE001
        raise HTTPException(500, f"本地 OCR 没跑起来：{e}") from e
    return {"text": hit["text"], "model": "rapidocr-local", "provider": "local"}


# ---------------- 会话 ----------------
@router.get("/sessions", summary="会话列表 / 搜索（登录后可用）")
def list_sessions(limit: int = 50, q: str = ""):
    if q.strip():
        return models.search_sessions(q.strip(), max(1, min(limit, 200)))
    return sessions.list_all(max(1, min(limit, 200)))


@router.post("/sessions", summary="新建会话（登录后可用）")
def create_session(body: SessionIn):
    return sessions.create(body.title or "新对话")


@router.get("/sessions/{sid}/messages", summary="会话消息")
def messages(sid: str):
    return sessions.messages(sid)


@router.delete("/sessions/{sid}", summary="删除会话")
def remove_session(sid: str):
    sessions.drop(sid)
    return {"ok": True}


@router.get("/export", summary="导出会话（Markdown / 纯文本 / Word）")
def export_session(sid: str, fmt: str = Query(default="md", pattern="^(md|txt|docx)$")):
    require("export")
    body = sessions.all_messages_text(sid)
    if not body:
        raise HTTPException(404, "这个会话还没有内容")
    title = sessions.title(sid) or "对话"
    stem = f"chat-{sid[:8]}"

    if fmt == "docx":
        data = docx_bytes(title, body.splitlines())
        return Response(
            content=data,
            media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            headers={"Content-Disposition": f'attachment; filename="{stem}.docx"'},
        )
    if fmt == "txt":
        text = f"{title}\n\n{body}\n"
        return Response(
            content=text.encode("utf-8"),
            media_type="text/plain; charset=utf-8",
            headers={"Content-Disposition": f'attachment; filename="{stem}.txt"'},
        )
    md = f"# {title}\n\n> 导出于 {time.strftime('%Y-%m-%d %H:%M')}\n\n{body}\n"
    return Response(
        content=md,
        media_type="text/markdown; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{stem}.md"'},
    )
