"""待办解析和小工具：把一句中文拆成时间、优先级、标签，顺手做冲突检测和日历导出。

不接第三方日历库，ICS 就按格式拼几行；规则能认常用说法，认不出来的留给页面上手动改。
"""
from __future__ import annotations

import csv
import io
import re
import time
from datetime import datetime, timedelta
from typing import Any

from .db import sqlite as db

_WEEK = {"一": 0, "二": 1, "三": 2, "四": 3, "五": 4, "六": 5, "日": 6, "天": 6}
_PERIOD = (("凌晨", 5), ("早上", 9), ("上午", 9), ("中午", 12), ("下午", 15), ("晚上", 19), ("傍晚", 18), ("夜里", 21))
_CN_NUM = {"零": 0, "一": 1, "二": 2, "两": 2, "三": 3, "四": 4, "五": 5, "六": 6, "七": 7, "八": 8, "九": 9, "十": 10}


def _midnight(ts: float) -> datetime:
    d = datetime.fromtimestamp(ts)
    return d.replace(hour=0, minute=0, second=0, microsecond=0)


def parse(text: str, now: float | None = None) -> dict[str, Any]:
    s = str(text or "").strip()
    stamp = now if now is not None else db.now()
    day = _midnight(stamp)
    rest = s

    # 日期
    if "大后天" in rest:
        day += timedelta(days=3)
        rest = rest.replace("大后天", "")
    elif "后天" in rest:
        day += timedelta(days=2)
        rest = rest.replace("后天", "")
    elif "明天" in rest or "明日" in rest:
        day += timedelta(days=1)
        rest = re.sub(r"明天|明日", "", rest)
    elif "今天" in rest or "今日" in rest:
        rest = re.sub(r"今天|今日", "", rest)
    else:
        m = re.search(r"下(?:周|星期)([一二三四五六日天])", rest)
        if m:
            delta = (_WEEK[m.group(1)] - day.weekday()) % 7 + 7
            day += timedelta(days=delta)
            rest = rest[: m.start()] + rest[m.end() :]
        else:
            m = re.search(r"(?:本)?(?:周|星期)([一二三四五六日天])", rest)
            if m:
                delta = (_WEEK[m.group(1)] - day.weekday()) % 7
                day += timedelta(days=delta)
                rest = rest[: m.start()] + rest[m.end() :]
            else:
                m = re.search(r"(\d{1,2})月(\d{1,2})[日号]", rest)
                if m:
                    try:
                        day = day.replace(month=int(m.group(1)), day=int(m.group(2)))
                        rest = rest[: m.start()] + rest[m.end() :]
                    except ValueError:
                        pass

    # 时段 + 几点几分
    hour, minute = 9, 0
    has_time = False
    for word, h in _PERIOD:
        if word in rest:
            hour, has_time = h, True
            rest = rest.replace(word, "")
            break
    m = re.search(r"(\d{1,2})\s*[点:：时]\s*(\d{1,2})?\s*分?", rest)
    if m:
        hour = int(m.group(1))
        minute = int(m.group(2) or 0)
        has_time = True
        rest = rest[: m.start()] + rest[m.end() :]
    else:
        m = re.search(r"([零一二三四五六七八九十]{1,3})\s*点\s*(半|\d{1,2})?", rest)
        if m:
            word = m.group(1)
            if word == "十":
                hour = 10
            elif word.startswith("十"):
                hour = 10 + _CN_NUM.get(word[1:], 0)
            else:
                hour = _CN_NUM.get(word, 9)
            tail = m.group(2) or ""
            minute = 30 if tail == "半" else (int(tail) if tail.isdigit() else 0)
            has_time = True
            rest = rest[: m.start()] + rest[m.end() :]
    if re.search(r"半", rest) and has_time:
        minute = 30
        rest = rest.replace("半", "", 1)

    due = day + timedelta(hours=hour, minutes=minute)
    if not has_time and "明天" not in s and "周" not in s and "月" not in s:
        # 只说“一会儿”“记得买奶”这种，按一小时后排，别塞到今天早上
        if due.timestamp() < stamp:
            due = datetime.fromtimestamp(stamp) + timedelta(hours=1)

    # 提前出门要先摘出来，不然会被下面的“时长”规则吃掉
    lead = 0
    m = re.search(r"(?:提前|预留)\s*(\d+|[一二三四五六七八九十]+)\s*分钟\s*(?:出门|出发|提醒)?", rest)
    if m:
        word = m.group(1)
        lead = int(word) if word.isdigit() else _CN_NUM.get(word, 0)
        rest = rest[: m.start()] + rest[m.end() :]

    # 时长
    duration = 30
    m = re.search(r"(\d+(?:\.\d+)?)\s*个?小时", rest)
    if m:
        duration = int(float(m.group(1)) * 60)
        rest = rest[: m.start()] + rest[m.end() :]
    else:
        m = re.search(r"(\d+)\s*分钟", rest)
        if m:
            duration = int(m.group(1))
            rest = rest[: m.start()] + rest[m.end() :]

    # 优先级 / 重复
    priority = "normal"
    if re.search(r"紧急|很急|高优先级|重要", rest):
        priority = "high"
        rest = re.sub(r"紧急|很急|高优先级|重要", "", rest)
    elif re.search(r"不急|低优先级", rest):
        priority = "low"
        rest = re.sub(r"不急|低优先级", "", rest)

    repeat = "once"
    for word, value in (("每天", "daily"), ("每日", "daily"), ("每周", "weekly"), ("每星期", "weekly"), ("每月", "monthly")):
        if word in rest:
            repeat = value
            rest = rest.replace(word, "")
            break

    tags = [x.strip() for x in re.findall(r"#([^\s#]+)", rest) if x.strip()]
    rest = re.sub(r"#[^\s#]+", "", rest)
    m = re.search(r"标签\s*[:：]\s*([^\s，,]+)", rest)
    if m:
        tags.extend(x for x in m.group(1).split(",") if x)
        rest = rest[: m.start()] + rest[m.end() :]

    title = re.sub(r"[，,。\s]+", " ", rest).strip(" ：:-,，。")
    if not title:
        title = s[:40]
    return {
        "title": title,
        "note": "",
        "due_at": round(due.timestamp(), 2),
        "end_at": round((due + timedelta(minutes=duration)).timestamp(), 2),
        "priority": priority,
        "tags": tags,
        "repeat": repeat,
        "lead_minutes": lead,
        "duration_minutes": duration,
    }


def next_due(row: dict[str, Any]) -> float | None:
    """重复事件完成后算下一次；一次性事件返回 None。"""
    repeat = row.get("repeat") or "once"
    ts = row.get("due_at")
    if not ts:
        return None
    d = datetime.fromtimestamp(float(ts))
    if repeat == "daily":
        d += timedelta(days=1)
    elif repeat == "weekly":
        d += timedelta(days=7)
    elif repeat == "monthly":
        y, m = (d.year + 1, 1) if d.month == 12 else (d.year, d.month + 1)
        d = d.replace(year=y, month=m)
    else:
        return None
    return d.timestamp()


def conflicts(due: float, end: float, exclude: str = "") -> list[dict[str, Any]]:
    rows = db.rows(
        "SELECT * FROM todos WHERE done=0 AND due_at IS NOT NULL AND end_at IS NOT NULL "
        "AND id<>? AND due_at<? AND end_at>? ORDER BY due_at LIMIT 20",
        (exclude, end, due),
    )
    return [
        {
            "id": r["id"],
            "title": r["title"],
            "due_at": r["due_at"],
            "end_at": r["end_at"],
        }
        for r in rows
    ]


def _ics_time(ts: float) -> str:
    return datetime.utcfromtimestamp(float(ts)).strftime("%Y%m%dT%H%M%SZ")


def to_ics(rows: list[dict[str, Any]]) -> str:
    out = ["BEGIN:VCALENDAR", "VERSION:2.0", "PRODID:-//StarClerk//Todos//CN"]
    for r in rows:
        if not r.get("due_at"):
            continue
        end = r.get("end_at") or float(r["due_at"]) + 1800
        out += [
            "BEGIN:VEVENT",
            f"UID:{r['id']}@starclerk",
            f"DTSTAMP:{_ics_time(db.now())}",
            f"DTSTART:{_ics_time(r['due_at'])}",
            f"DTEND:{_ics_time(end)}",
            f"SUMMARY:{str(r['title']).replace(chr(10), ' ')}",
            f"DESCRIPTION:{str(r.get('note') or '').replace(chr(10), ' ')}",
            "END:VEVENT",
        ]
    out.append("END:VCALENDAR")
    return "\r\n".join(out) + "\r\n"


def to_csv(rows: list[dict[str, Any]]) -> bytes:
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(["标题", "开始", "结束", "优先级", "标签", "重复", "提前分钟", "备注"])
    for r in rows:
        fmt = lambda v: datetime.fromtimestamp(float(v)).strftime("%Y-%m-%d %H:%M") if v else ""
        w.writerow(
            [
                r["title"],
                fmt(r.get("due_at")),
                fmt(r.get("end_at")),
                r.get("priority"),
                r.get("tags"),
                r.get("repeat"),
                r.get("lead_minutes") or 0,
                r.get("note") or "",
            ]
        )
    return b"\xef\xbb\xbf" + buf.getvalue().encode("utf-8")
