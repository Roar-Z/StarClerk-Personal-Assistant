"""未登录免费模型额度：Kilo 免费档每小时 200 次，未登录只能花一半。

为什么放在内存里：Kilo 的免费额度本来就是按小时、按 IP 算的，
本地跟着同一个窗口卡就行；未登录会话也不落库，没必要为它单开一张表。
进程重启就从零开始，自己调试的时候也方便。
"""
from __future__ import annotations

import threading
import time
from collections import deque

from fastapi import HTTPException

from .config import settings

WINDOW = 3600  # 一小时一个窗口，跟 Kilo 免费档对齐

_lock = threading.Lock()
_hits: deque[float] = deque()  # 只存时间戳，窗口滑过去就扔掉


def _prune(now: float) -> None:
    while _hits and now - _hits[0] > WINDOW:
        _hits.popleft()


def total() -> int:
    """免费档每小时的总次数，换网关就改 .env 里的 GUEST_HOURLY_LIMIT。"""
    return max(2, settings.guest_hourly_limit)


def limit() -> int:
    """未登录只拿一半，剩下那一半留给登录后的用户，别让试用把整池吃干净。"""
    return max(1, total() // 2)


def used() -> int:
    with _lock:
        _prune(time.time())
        return len(_hits)


def snapshot() -> dict:
    """给前端显示"还剩几次"，同时带上模型名，省得再查一次配置。"""
    now = time.time()
    with _lock:
        _prune(now)
        n = len(_hits)
        reset_in = int(WINDOW - (now - _hits[0])) if _hits else WINDOW
    cap = limit()
    return {
        "model": settings.guest_llm_model,
        "limit": cap,
        "total": total(),
        "used": n,
        "left": max(0, cap - n),
        "window": WINDOW,
        "reset_in": max(0, reset_in),
    }


def check() -> None:
    """对话入口先看额度，用完了直接 429，别等网关那边报错再翻译。"""
    info = snapshot()
    if info["used"] < info["limit"]:
        return
    wait = info["reset_in"] // 60 + 1
    raise HTTPException(
        429,
        f"未登录每小时可用 {info['limit']} 次免费模型（另一半留给登录用户），"
        f"大概 {wait} 分钟后恢复，或者到「模型」页登录",
    )


def hit() -> None:
    """答完再记一次，模型报错的那次不算，别冤枉用户。"""
    with _lock:
        _hits.append(time.time())


def reset() -> None:
    with _lock:
        _hits.clear()
