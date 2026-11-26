"""学习空间配置：开关、考试时段、cookie、运行日志，都存在本地 kv 表。

只存必要字段，cookie 是扫码登录拿到的那一串，重启程序不会丢。
"""
from __future__ import annotations

import time
from typing import Any

from ..db import models as meta

KEY_ENABLED = "study.enabled"        # 定时模式总开关
KEY_COOKIE = "study.cookie"          # 学习通网页会话 cookie
KEY_COOKIE_AT = "study.cookie_at"
KEY_EXAMS = "study.exams"            # 考试时段列表
KEY_LOGS = "study.logs"              # 运行日志
KEY_LAST = "study.last_sync"         # 最近一次同步结果

LOG_LIMIT = 300


def enabled() -> bool:
    return bool(meta.kv_get(KEY_ENABLED, False))


def set_enabled(v: bool) -> None:
    meta.kv_set(KEY_ENABLED, bool(v))


def cookie() -> str:
    return str(meta.kv_get(KEY_COOKIE, "") or "")


def set_cookie(value: str) -> None:
    meta.kv_set(KEY_COOKIE, value or "")
    meta.kv_set(KEY_COOKIE_AT, time.time() if value else 0)


def cookie_info() -> dict[str, Any]:
    return {"logged_in": bool(cookie()), "at": meta.kv_get(KEY_COOKIE_AT, 0)}


def exams() -> list[dict[str, Any]]:
    v = meta.kv_get(KEY_EXAMS, [])
    return v if isinstance(v, list) else []


def set_exams(items: list[dict[str, Any]]) -> None:
    meta.kv_set(KEY_EXAMS, items)


def logs() -> list[dict[str, Any]]:
    v = meta.kv_get(KEY_LOGS, [])
    return v if isinstance(v, list) else []


def add_log(status: str, reason: str, new: int = 0, detail: str = "") -> None:
    """每条日志记时间、状态、是否拿到新作业，页面和 app.log 都留一份。"""
    import logging

    row = {
        "at": time.time(),
        "status": status,
        "reason": reason,
        "new": int(new),
        "detail": str(detail)[:200],
    }
    v = logs()
    v.insert(0, row)
    meta.kv_set(KEY_LOGS, v[:LOG_LIMIT])
    logging.getLogger("study").info(
        "[学习通] %s | %s | 新作业 %d | %s", reason, status, row["new"], detail
    )


def last_sync() -> dict[str, Any]:
    return meta.kv_get(KEY_LAST, {}) or {}


def set_last_sync(v: dict[str, Any]) -> None:
    meta.kv_set(KEY_LAST, v)


def in_exam(now: float | None = None) -> dict[str, Any] | None:
    """考试保护：命中任意一段考试时段就返回那一段，外部据此跳过请求。"""
    now = time.time() if now is None else now
    for item in exams():
        try:
            start = float(item.get("start") or 0)
            end = float(item.get("end") or 0)
        except (TypeError, ValueError):
            continue
        if start and end and start <= now <= end:
            return item
    return None
