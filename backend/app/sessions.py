"""会话仓储：免费版落 SQLite，未登录只放进程内存。

游客的会话 id 统一带 g- 前缀，一看就知道去内存里找，不用再问一遍档位。
"""
from __future__ import annotations

import threading
import time
import uuid
from typing import Any

from .db import models as meta
from .db import sqlite as db

_GUEST_PREFIX = "g-"
_lock = threading.Lock()
_memory: dict[str, dict[str, Any]] = {}


def is_guest(sid: str) -> bool:
    return str(sid).startswith(_GUEST_PREFIX)


def new_guest(title: str = "新对话") -> dict[str, Any]:
    sid = f"{_GUEST_PREFIX}{uuid.uuid4().hex[:10]}"
    item = {"id": sid, "title": title, "messages": [], "created_at": time.time(), "updated_at": time.time()}
    with _lock:
        _memory[sid] = item
    return {"id": sid, "title": title, "created_at": item["created_at"], "updated_at": item["updated_at"]}


def create(title: str = "新对话") -> dict[str, Any]:
    from . import license

    if license.is_guest():
        return new_guest(title)
    return meta.create_session(title)


def title(sid: str) -> str:
    if is_guest(sid):
        with _lock:
            return str((_memory.get(sid) or {}).get("title") or "对话")
    row = meta.get_session(sid) or {}
    return str(row.get("title") or "对话")


def touch_title(sid: str, title: str) -> None:
    if is_guest(sid):
        with _lock:
            if sid in _memory:
                _memory[sid]["title"] = title[:60]
        return
    meta.rename_session(sid, title)


def append(sid: str, role: str, content: str) -> None:
    if not is_guest(sid):
        meta.add_message(sid, role, content)  # type: ignore[arg-type]
        return
    with _lock:
        item = _memory.get(sid) or _memory.setdefault(
            sid, {"id": sid, "title": "新对话", "messages": [], "created_at": time.time(), "updated_at": time.time()}
        )
        item["messages"].append({"role": role, "content": content, "created_at": time.time()})
        item["updated_at"] = time.time()


def history(sid: str, limit: int = 10) -> list[dict[str, str]]:
    if not is_guest(sid):
        return meta.history(sid, limit)
    with _lock:
        item = _memory.get(sid) or {}
        msgs = item.get("messages") or []
    return [{"role": m["role"], "content": m["content"]} for m in msgs[-limit:]]


def messages(sid: str) -> list[dict[str, Any]]:
    if not is_guest(sid):
        return db.rows("SELECT * FROM messages WHERE session_id=? ORDER BY created_at", (sid,))
    with _lock:
        item = _memory.get(sid) or {}
        raw = list(item.get("messages") or [])
    return [
        {"id": f"{sid}-{i}", "session_id": sid, "role": m["role"], "content": m["content"],
         "created_at": m["created_at"]}
        for i, m in enumerate(raw)
    ]


def drop(sid: str) -> None:
    if not is_guest(sid):
        meta.delete_session(sid)
        return
    with _lock:
        _memory.pop(sid, None)


def list_all(limit: int = 50) -> list[dict[str, Any]]:
    from . import license

    if license.is_guest():  # 理论上被中间件挡掉了，这里再兜一层
        return []
    return meta.list_sessions(limit)


def count() -> int:
    from . import license

    if license.is_guest():
        with _lock:
            return len(_memory)
    return len(meta.list_sessions(1000))


def all_messages_text(sid: str) -> str:
    """导出 Markdown 用：拼成一段纯文本，标题加粗。"""
    rows = messages(sid)
    if not rows:
        return ""
    lines = []
    for m in rows:
        who = "我" if m["role"] == "user" else "StarClerk"
        lines.append(f"**{who}**\n\n{m['content']}")
    return "\n\n---\n\n".join(lines)
