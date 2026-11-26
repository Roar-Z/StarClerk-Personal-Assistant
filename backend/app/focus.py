"""专注番茄钟：25 分钟专注 + 5 分钟短休，每 4 个番茄 15 分钟长休。

会话和完成的番茄都存在 kv 表，重启程序还能接着看统计。
时间按时间戳算，前端切页不会把倒计时走歪。
"""
from __future__ import annotations

import time
from datetime import datetime, timedelta
from typing import Any

from .db import models as meta

KEY_SESSION = "focus.session"
KEY_RECORDS = "focus.records"

FOCUS_MIN = 25
SHORT_BREAK = 5
LONG_BREAK = 15
LONG_EVERY = 4


def session() -> dict[str, Any]:
    v = meta.kv_get(KEY_SESSION, {})
    return v if isinstance(v, dict) else {}


def _save(v: dict[str, Any]) -> None:
    meta.kv_set(KEY_SESSION, v)


def records() -> list[dict[str, Any]]:
    v = meta.kv_get(KEY_RECORDS, [])
    return v if isinstance(v, list) else []


def start(minutes: int, mode: str = "focus") -> dict[str, Any]:
    """开始一段专注或休息。minutes 用分钟传，前端显示倒计时。"""
    minutes = max(1, min(int(minutes or FOCUS_MIN), 180))
    if mode not in ("focus", "short", "long"):
        mode = "focus"
    now = time.time()
    v = {
        "active": True,
        "mode": mode,
        "minutes": minutes,
        "started_at": now,
        "end_at": now + minutes * 60,
        "paused_at": 0,
        "paused_total": 0,
    }
    _save(v)
    return v


def pause() -> dict[str, Any]:
    v = session()
    if v.get("active") and not v.get("paused_at"):
        v["paused_at"] = time.time()
        _save(v)
    return v


def resume() -> dict[str, Any]:
    v = session()
    if v.get("active") and v.get("paused_at"):
        now = time.time()
        v["paused_total"] = int(v.get("paused_total") or 0) + int(now - float(v["paused_at"]))
        v["end_at"] = float(v["end_at"]) + (now - float(v["paused_at"]))
        v["paused_at"] = 0
        _save(v)
    return v


def stop() -> dict[str, Any]:
    """结束当前段。只有专注段且没暂停才算一个完整番茄。"""
    v = session()
    if not v.get("active"):
        return v
    ended = time.time()
    complete = False
    if v.get("mode") == "focus" and not v.get("paused_at"):
        planned = int(v.get("minutes") or FOCUS_MIN) * 60
        actual = ended - float(v["started_at"]) - int(v.get("paused_total") or 0)
        complete = actual >= planned * 0.9
    if complete:
        add_record(int(v.get("minutes") or FOCUS_MIN), ended)
    v = {"active": False, "mode": v.get("mode"), "last_complete": complete, "ended_at": ended}
    _save(v)
    return v


def add_record(minutes: int, at: float | None = None) -> None:
    at = time.time() if at is None else at
    v = records()
    v.append({"at": at, "minutes": int(minutes), "date": datetime.fromtimestamp(at).strftime("%Y-%m-%d")})
    # 只留最近 2000 条，够统计几年了
    meta.kv_set(KEY_RECORDS, v[-2000:])


def stats(days: int = 7) -> dict[str, Any]:
    """今日、本周趋势、累计番茄数。符合常见番茄钟统计口径。"""
    days = max(1, min(int(days or 7), 90))
    today = datetime.now().date()
    all_rows = records()
    total_min = sum(int(r.get("minutes") or 0) for r in all_rows)
    today_min = sum(int(r.get("minutes") or 0) for r in all_rows if r.get("date") == today.strftime("%Y-%m-%d"))

    daily = []
    for i in range(days - 1, -1, -1):
        d = today - timedelta(days=i)
        key = d.strftime("%Y-%m-%d")
        rows = [r for r in all_rows if r.get("date") == key]
        daily.append({
            "date": key,
            "minutes": sum(int(r.get("minutes") or 0) for r in rows),
            "count": len(rows),
        })

    # 连续打卡天数
    streak = 0
    have = {r.get("date") for r in all_rows}
    d = today
    while d.strftime("%Y-%m-%d") in have:
        streak += 1
        d -= timedelta(days=1)

    return {
        "today_minutes": today_min,
        "today_count": sum(1 for r in all_rows if r.get("date") == today.strftime("%Y-%m-%d")),
        "total_minutes": total_min,
        "total_count": len(all_rows),
        "streak": streak,
        "daily": daily,
        "defaults": {"focus": FOCUS_MIN, "short": SHORT_BREAK, "long": LONG_BREAK, "long_every": LONG_EVERY},
    }
