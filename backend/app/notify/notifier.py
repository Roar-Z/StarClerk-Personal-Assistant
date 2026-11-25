"""主动提醒出口：托盘气泡 + 前端 SSE 弹层，二选一都不阻塞。

调用方（调度器/工具）只管 notify()，不需要知道当前有没有窗口。
"""
from __future__ import annotations

import asyncio
import logging
import queue
from typing import Any

log = logging.getLogger("notify")

_icon: Any = None
_queues: list[asyncio.Queue] = []
_loop: asyncio.AbstractEventLoop | None = None
_pending: queue.Queue = queue.Queue()  # 事件循环未就绪（如启动阶段）时暂存


def bind_loop(loop: asyncio.AbstractEventLoop) -> None:
    global _loop
    _loop = loop


def bind_icon(icon: Any) -> None:
    global _icon
    _icon = icon


def subscribe() -> asyncio.Queue:
    q: asyncio.Queue = asyncio.Queue(maxsize=50)
    _queues.append(q)
    return q


def unsubscribe(q: asyncio.Queue) -> None:
    if q in _queues:
        _queues.remove(q)


def _push(event: dict) -> None:
    for q in list(_queues):
        try:
            q.put_nowait(event)
        except asyncio.QueueFull:
            pass


def notify(title: str, body: str, level: str = "info") -> None:
    log.info("提醒：%s | %s", title, body)
    event = {"type": "notify", "level": level, "title": title, "body": body}
    if _icon is not None:
        try:
            _icon.notify(body[:200], title[:60])
        except Exception:  # noqa: BLE001  无托盘时忽略
            pass
    if _loop and _loop.is_running():
        _loop.call_soon_threadsafe(_push, event)
    else:
        _pending.put(event)


def drain_pending() -> None:
    while not _pending.empty():
        _push(_pending.get_nowait())
