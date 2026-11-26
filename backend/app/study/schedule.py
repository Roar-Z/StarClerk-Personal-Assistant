"""课表读取 + 日历导出。

走网页端课表接口，按周读取整学期的课，结果缓存本机。
请求策略保守：只在用户主动点导出时发请求；两次导出至少隔 5 分钟；
逐周串行、每周之间歇一下；一次失败就停，不做重试；复用已保存的网页会话。
不碰视频、答题、签到、提交这些写操作。
"""
from __future__ import annotations

import json
import time
from datetime import datetime, timedelta
from typing import Any

from ..db import models as meta
from . import chaoxing, store

# 网页端课表接口，平台改版时改这里
LESSONS = "https://kb.chaoxing.com/pc/curriculum/getMyLessons"

MIN_INTERVAL = 300          # 两次导出至少隔 5 分钟
WEEK_GAP = 0.6              # 每周之间歇 0.6 秒，别连着打
MAX_WEEKS = 30
KEY_LAST_FETCH = "study.schedule_fetch_at"
KEY_TERM_START = "study.term_start"   # 第一周周一的日期，YYYY-MM-DD
KEY_CACHE = "study.schedule_cache"    # 课表缓存，避免重复拉

WEEKDAYS = ["MO", "TU", "WE", "TH", "FR", "SA", "SU"]
# 高校常见节次时间，接口没给具体时间时用这个兜底
SECTIONS = {
    1: ("08:00", "08:45"), 2: ("08:55", "09:40"),
    3: ("10:00", "10:45"), 4: ("10:55", "11:40"),
    5: ("14:00", "14:45"), 6: ("14:55", "15:40"),
    7: ("16:00", "16:45"), 8: ("16:55", "17:40"),
    9: ("19:00", "19:45"), 10: ("19:55", "20:40"),
    11: ("20:50", "21:35"),
}


class TooFrequent(Exception):
    """两次导出间隔太短，让用户等会儿再点。"""


def term_start() -> str:
    return str(meta.kv_get(KEY_TERM_START, "") or "")


def set_term_start(value: str) -> None:
    meta.kv_set(KEY_TERM_START, value or "")


def cached() -> list[dict[str, Any]]:
    v = meta.kv_get(KEY_CACHE, [])
    return v if isinstance(v, list) else []


def can_fetch(now: float | None = None) -> bool:
    now = time.time() if now is None else now
    last = float(meta.kv_get(KEY_LAST_FETCH, 0) or 0)
    return not last or now - last >= MIN_INTERVAL


def fetch(weeks: int = 20, force: bool = False) -> list[dict[str, Any]]:
    """按周读课表。有缓存就直接用，不重复请求。"""
    weeks = max(1, min(int(weeks or 20), MAX_WEEKS))
    if not force and cached():
        return cached()

    now = time.time()
    if not can_fetch(now):
        left = MIN_INTERVAL - int(now - float(meta.kv_get(KEY_LAST_FETCH, 0) or 0))
        raise TooFrequent(f"请 {left} 秒后再导出")
    cookie = store.cookie()
    if not cookie:
        raise chaoxing.SessionExpired("还没扫码登录")

    meta.kv_set(KEY_LAST_FETCH, now)  # 不管成败都记，防止失败后连续点
    all_rows: list[dict[str, Any]] = []
    for week in range(1, weeks + 1):
        if week > 1:
            time.sleep(WEEK_GAP)
        with chaoxing._client(cookie) as c:
            res = c.get(LESSONS, params={"week": week}, headers={"Referer": "https://kb.chaoxing.com/pc/curriculum"})
            chaoxing._check(res)
            try:
                data = res.json()
            except ValueError as e:  # noqa: BLE001
                raise ValueError("课表返回不是 JSON，接口可能改版") from e
        rows = _parse(data, week)
        all_rows.extend(rows)

    # 去重：课程名 + 周 + 周几 + 开始节次 + 地点
    seen: set[str] = set()
    out: list[dict[str, Any]] = []
    for r in all_rows:
        key = f"{r['name']}|{r['week']}|{r['day']}|{r['s1']}|{r['room']}"
        if key not in seen:
            seen.add(key)
            out.append(r)
    meta.kv_set(KEY_CACHE, out)
    return out


def clear_cache() -> None:
    meta.kv_set(KEY_CACHE, [])


def _parse(data: Any, week: int) -> list[dict[str, Any]]:
    """解析 data.lessonArray，兼容常见字段别名。"""
    if isinstance(data, dict):
        payload = data.get("data") or {}
        rows = payload.get("lessonArray") if isinstance(payload, dict) else None
        if rows is None:
            rows = data.get("lessonArray") or data.get("list") or []
    elif isinstance(data, list):
        rows = data
    else:
        rows = []

    out: list[dict[str, Any]] = []
    for r in rows:
        if not isinstance(r, dict):
            continue
        name = str(r.get("name") or r.get("courseName") or "").strip()
        if not name:
            continue
        def to_int(v: Any, default: int) -> int:
            try:
                return int(v)
            except (TypeError, ValueError):
                return default

        out.append({
            "name": name,
            "teacher": str(r.get("teacherName") or r.get("teacher") or "").strip(),
            "room": str(r.get("location") or r.get("room") or "").strip(),
            "week": week,
            "day": max(1, min(to_int(r.get("dayOfWeek"), 1), 7)),
            "s1": max(1, min(to_int(r.get("beginNumber") or r.get("startSection"), 1), 11)),
            "s2": max(1, min(to_int(r.get("endNumber") or r.get("endSection"), to_int(r.get("beginNumber"), 1)), 11)),
        })
    return out


def _ics_time(d: datetime) -> str:
    return d.strftime("%Y%m%dT%H%M%S")


def to_ics(courses: list[dict[str, Any]], start_date: str) -> str:
    """按每周实际课生成 VEVENT，不用 RRULE，跟网页端看到的课表一致。"""
    if not start_date:
        raise ValueError("请先填学期第一周周一的日期")
    try:
        monday = datetime.strptime(start_date, "%Y-%m-%d")
    except ValueError as e:  # noqa: BLE001
        raise ValueError("日期格式应为 YYYY-MM-DD") from e

    out = ["BEGIN:VCALENDAR", "VERSION:2.0", "PRODID:-//StarClerk//Schedule//CN", "CALSCALE:GREGORIAN"]
    stamp = datetime.utcnow().strftime("%Y%m%dT%H%M%SZ")
    for i, c in enumerate(courses):
        t1, _ = SECTIONS.get(c["s1"], ("08:00", "08:45"))
        _, t2 = SECTIONS.get(c["s2"], ("09:40", "09:40"))
        try:
            sh, sm = [int(x) for x in t1.split(":")[:2]]
            eh, em = [int(x) for x in t2.split(":")[:2]]
        except (ValueError, IndexError):
            sh, sm, eh, em = 8, 0, 8, 45
        day = monday + timedelta(weeks=max(0, c.get("week", 1) - 1), days=c["day"] - 1)
        ds = day.replace(hour=sh, minute=sm)
        de = day.replace(hour=eh, minute=em)
        desc = "教师：" + (c.get("teacher") or "—") + "；第 " + str(c.get("week", 1)) + " 周"
        out += [
            "BEGIN:VEVENT",
            f"UID:schedule-{i}-{int(ds.timestamp())}@starclerk",
            f"DTSTAMP:{stamp}",
            f"DTSTART:{_ics_time(ds)}",
            f"DTEND:{_ics_time(de)}",
            f"SUMMARY:{c['name'].replace(chr(10), ' ')}",
            f"LOCATION:{c.get('room', '').replace(chr(10), ' ')}",
            f"DESCRIPTION:{desc.replace(chr(10), ' ')}",
            "END:VEVENT",
        ]
    out.append("END:VCALENDAR")
    return "\r\n".join(out) + "\r\n"
