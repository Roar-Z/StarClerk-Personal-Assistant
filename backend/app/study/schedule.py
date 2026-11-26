"""课表读取 + 日历导出。

请求策略走保守路线，降低触发平台风控的概率：
只在用户主动点导出时发请求；两次导出之间至少隔 5 分钟；一次只发一个请求；
串行、不并发、失败不重试；复用已保存的网页会话，不重复登录。
不碰视频、答题、签到、提交这些写操作。
"""
from __future__ import annotations

import time
from datetime import datetime, timedelta
from typing import Any

from ..db import models as meta
from . import chaoxing, store

# 课程表接口，平台改版时改这里
SCHEDULE = "https://mooc1.chaoxing.com/mooc-ans/courseSchedule/student/list"

MIN_INTERVAL = 300          # 两次导出至少隔 5 分钟
KEY_LAST_FETCH = "study.schedule_fetch_at"
KEY_TERM_START = "study.term_start"   # 第一周周一的日期，YYYY-MM-DD

WEEKDAYS = ["MO", "TU", "WE", "TH", "FR", "SA", "SU"]
# 高校常见节次时间，接口没给具体时间时用这个兜底
SECTIONS = {
    1: ("08:00", "08:45"), 2: ("08:50", "09:35"),
    3: ("10:00", "10:45"), 4: ("10:50", "11:35"),
    5: ("14:00", "14:45"), 6: ("14:50", "15:35"),
    7: ("16:00", "16:45"), 8: ("16:50", "17:35"),
    9: ("19:00", "19:45"), 10: ("19:50", "20:35"),
}


class TooFrequent(Exception):
    """两次导出间隔太短，让用户等会儿再点。"""


def term_start() -> str:
    return str(meta.kv_get(KEY_TERM_START, "") or "")


def set_term_start(value: str) -> None:
    meta.kv_set(KEY_TERM_START, value or "")


def can_fetch(now: float | None = None) -> bool:
    now = time.time() if now is None else now
    last = float(meta.kv_get(KEY_LAST_FETCH, 0) or 0)
    return not last or now - last >= MIN_INTERVAL


def fetch() -> list[dict[str, Any]]:
    """只读一次课表，不做任何重试。登录失效抛 SessionExpired。"""
    now = time.time()
    if not can_fetch(now):
        left = MIN_INTERVAL - int(now - float(meta.kv_get(KEY_LAST_FETCH, 0) or 0))
        raise TooFrequent(f"请 {left} 秒后再导出")
    cookie = store.cookie()
    if not cookie:
        raise chaoxing.SessionExpired("还没扫码登录")

    meta.kv_set(KEY_LAST_FETCH, now)  # 不管成败都记，防止失败后连续点
    with chaoxing._client(cookie) as c:
        res = c.get(SCHEDULE, headers={"Referer": "https://mooc1.chaoxing.com/mooc-ans/courseSchedule"})
        chaoxing._check(res)
        try:
            data = res.json()
        except ValueError as e:  # noqa: BLE001
            raise ValueError("课表返回不是 JSON，接口可能改版") from e
        return _parse(data)


def _parse(data: Any) -> list[dict[str, Any]]:
    rows = data if isinstance(data, list) else (
        data.get("list") or data.get("data") or data.get("rows") or []
        if isinstance(data, dict) else []
    )
    out: list[dict[str, Any]] = []
    for r in rows:
        if not isinstance(r, dict):
            continue
        name = str(r.get("courseName") or r.get("name") or r.get("course") or "").strip()
        if not name:
            continue
        day = r.get("dayOfWeek") or r.get("weekday") or r.get("day") or 1
        try:
            day = int(day)
        except (TypeError, ValueError):
            day = 1
        day = max(1, min(day, 7))
        s1 = r.get("startSection") or r.get("startSectionNum") or r.get("start") or 1
        s2 = r.get("endSection") or r.get("endSectionNum") or r.get("end") or s1
        try:
            s1, s2 = int(s1), int(s2)
        except (TypeError, ValueError):
            s1 = s2 = 1
        w1 = r.get("startWeek") or r.get("beginWeek") or 1
        w2 = r.get("endWeek") or r.get("weeks") or 16
        try:
            w1, w2 = int(w1), int(w2)
        except (TypeError, ValueError):
            w1, w2 = 1, 16
        out.append({
            "name": name,
            "teacher": str(r.get("teacherName") or r.get("teacher") or "").strip(),
            "room": str(r.get("classroom") or r.get("room") or r.get("place") or "").strip(),
            "day": day,
            "s1": s1,
            "s2": s2,
            "w1": w1,
            "w2": w2,
            "start_time": str(r.get("startTime") or "").strip(),
            "end_time": str(r.get("endTime") or "").strip(),
        })
    return out


def _ics_time(d: datetime) -> str:
    return d.strftime("%Y%m%dT%H%M%S")


def to_ics(courses: list[dict[str, Any]], start_date: str) -> str:
    """生成每周重复的日历事件，用 RRULE 避免展开成几十条。"""
    if not start_date:
        raise ValueError("请先填学期第一周周一的日期")
    try:
        monday = datetime.strptime(start_date, "%Y-%m-%d")
    except ValueError as e:  # noqa: BLE001
        raise ValueError("日期格式应为 YYYY-MM-DD") from e

    out = ["BEGIN:VCALENDAR", "VERSION:2.0", "PRODID:-//StarClerk//Schedule//CN", "CALSCALE:GREGORIAN"]
    stamp = datetime.utcnow().strftime("%Y%m%dT%H%M%SZ")
    for i, c in enumerate(courses):
        t1, t2 = SECTIONS.get(c["s1"], ("08:00", "08:45"))
        start_hm = c.get("start_time") or t1
        end_hm = c.get("end_time") or SECTIONS.get(c["s2"], (t2, "09:30"))[1]
        try:
            sh, sm = [int(x) for x in start_hm.split(":")[:2]]
            eh, em = [int(x) for x in end_hm.split(":")[:2]]
        except (ValueError, IndexError):
            sh, sm, eh, em = 8, 0, 8, 45
        first = monday + timedelta(days=c["day"] - 1, weeks=max(0, c["w1"] - 1))
        ds = first.replace(hour=sh, minute=sm)
        de = first.replace(hour=eh, minute=em)
        until = monday + timedelta(weeks=max(0, c["w2"] - 1), days=7)
        desc = "教师：" + (c.get("teacher") or "—")
        out += [
            "BEGIN:VEVENT",
            f"UID:schedule-{i}-{int(ds.timestamp())}@starclerk",
            f"DTSTAMP:{stamp}",
            f"DTSTART:{_ics_time(ds)}",
            f"DTEND:{_ics_time(de)}",
            f"RRULE:FREQ=WEEKLY;BYDAY={WEEKDAYS[c['day'] - 1]};UNTIL={_ics_time(until)}",
            f"SUMMARY:{c['name'].replace(chr(10), ' ')}",
            f"LOCATION:{c.get('room', '').replace(chr(10), ' ')}",
            f"DESCRIPTION:{desc.replace(chr(10), ' ')}",
            "END:VEVENT",
        ]
    out.append("END:VCALENDAR")
    return "\r\n".join(out) + "\r\n"
