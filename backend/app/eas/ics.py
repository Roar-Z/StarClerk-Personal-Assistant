"""教务课表导出日历：按周次和单双周展开成 VEVENT。"""
from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any

SECTIONS = {
    1: ("08:00", "08:45"), 2: ("08:55", "09:40"),
    3: ("10:00", "10:45"), 4: ("10:55", "11:40"),
    5: ("14:00", "14:45"), 6: ("14:55", "15:40"),
    7: ("16:00", "16:45"), 8: ("16:55", "17:40"),
    9: ("19:00", "19:45"), 10: ("19:55", "20:40"),
    11: ("20:50", "21:35"),
}


def export(courses: list[dict[str, Any]], start_date: str) -> str:
    if not start_date:
        raise ValueError("请先填学期第一周周一的日期")
    try:
        monday = datetime.strptime(start_date, "%Y-%m-%d")
    except ValueError as e:  # noqa: BLE001
        raise ValueError("日期格式应为 YYYY-MM-DD") from e

    out = ["BEGIN:VCALENDAR", "VERSION:2.0", "PRODID:-//StarClerk//EAS//CN", "CALSCALE:GREGORIAN"]
    stamp = datetime.utcnow().strftime("%Y%m%dT%H%M%SZ")
    n = 0
    for c in courses:
        s1 = int(c.get("s1") or 1)
        s2 = int(c.get("s2") or s1)
        t1 = SECTIONS.get(s1, ("08:00", "08:45"))[0]
        t2 = SECTIONS.get(s2, ("09:40", "09:40"))[1]
        sh, sm = [int(x) for x in t1.split(":")]
        eh, em = [int(x) for x in t2.split(":")]
        parity = str(c.get("parity") or "")
        for week in range(int(c.get("w1") or 1), int(c.get("w2") or 16) + 1):
            if parity == "单" and week % 2 == 0:
                continue
            if parity == "双" and week % 2 == 1:
                continue
            day = monday + timedelta(weeks=week - 1, days=int(c.get("day") or 1) - 1)
            ds = day.replace(hour=sh, minute=sm)
            de = day.replace(hour=eh, minute=em)
            desc = " / ".join(x for x in (c.get("teacher"), f"第{week}周") if x)
            out += [
                "BEGIN:VEVENT",
                f"UID:eas-{n}@starclerk",
                f"DTSTAMP:{stamp}",
                f"DTSTART:{ds:%Y%m%dT%H%M%S}",
                f"DTEND:{de:%Y%m%dT%H%M%S}",
                f"SUMMARY:{str(c.get('name', '')).replace(chr(10), ' ')}",
                f"LOCATION:{str(c.get('room', '')).replace(chr(10), ' ')}",
                f"DESCRIPTION:{desc.replace(chr(10), ' ')}",
                "END:VEVENT",
            ]
            n += 1
    out.append("END:VCALENDAR")
    return "\r\n".join(out) + "\r\n"
