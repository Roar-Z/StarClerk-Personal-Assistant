"""课表 HTML 解析：兼容老式教务表格（正方/强智风格）。

不依赖第三方库，用标准库 html.parser 把表格读成二维格子，再按常见表头定位
星期和节次，从单元格文字里抠课程名、教师、教室、周次、单双周。
广科教务是这种老式表格，先按通用规则走；遇到特殊结构再补这里。
"""
from __future__ import annotations

import re
from html.parser import HTMLParser
from typing import Any

WEEK_WORDS = [
    ("星期一", 1), ("周二", 2), ("星期三", 3), ("周四", 4),
    ("星期五", 5), ("周六", 6), ("星期日", 7), ("星期天", 7), ("周日", 7), ("周天", 7),
    ("周一", 1), ("星期三", 3), ("星期二", 2), ("星期四", 4), ("星期五", 5),
    ("星期六", 6), ("周七", 7),
    ("一", 1), ("二", 2), ("三", 3), ("四", 4), ("五", 5), ("六", 6), ("日", 7), ("天", 7),
]
SECTION_RE = re.compile(r"(?:第)?\s*(\d+)\s*(?:[-~至到]\s*\d+)?\s*节")
WEEK_RE = re.compile(r"第?\s*(\d+)\s*[-~至到]\s*(\d+)\s*周")
SINGLE_RE = re.compile(r"(单|双)(?:周)?")
BRACE_RE = re.compile(r"[{}（）()【】\[\]]")


class _TableParser(HTMLParser):
    """收集所有 table 的行列文本，顺便记下行跨度。"""

    def __init__(self) -> None:
        super().__init__()
        self.tables: list[list[list[str]]] = []
        self._depth = 0
        self._rows: list[list[str]] = []
        self._row: list[str] | None = None
        self._buf: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag == "table":
            self._depth += 1
            if self._depth == 1:
                self._rows = []
        elif tag == "tr" and self._depth == 1:
            self._row = []
        elif tag in ("td", "th") and self._depth == 1 and self._row is not None:
            self._buf = []

    def handle_data(self, data: str) -> None:
        if self._depth == 1 and self._buf is not None:
            self._buf.append(data)

    def handle_endtag(self, tag: str) -> None:
        if tag in ("td", "th") and self._depth == 1 and self._row is not None:
            self._row.append(" ".join("".join(self._buf).split()))
            self._buf = []  # type: ignore[assignment]
        elif tag == "tr" and self._depth == 1 and self._row is not None:
            if self._row:
                self._rows.append(self._row)
            self._row = None
        elif tag == "table" and self._depth:
            if self._depth == 1:
                self.tables.append(self._rows)
            self._depth -= 1


def parse(html: str) -> list[dict[str, Any]]:
    p = _TableParser()
    try:
        p.feed(html or "")
    except Exception:  # noqa: BLE001  HTML 不规范时也尽量用读到的部分
        pass
    best: list[dict[str, Any]] = []
    for rows in p.tables:
        if len(rows) < 3:
            continue
        got = _from_grid(rows)
        if len(got) > len(best):
            best = got
    return _dedup(best)


def _day(text: str) -> int:
    t = text.strip()
    for word, num in WEEK_WORDS:
        if word in t:
            return num
    return 0


def _from_grid(grid: list[list[str]]) -> list[dict[str, Any]]:
    # 找星期表头行：出现至少 3 个星期词
    day_row = -1
    day_cols: dict[int, int] = {}
    for i, row in enumerate(grid[:6]):
        found: dict[int, int] = {}
        for j, cell in enumerate(row):
            d = _day(cell)
            if d:
                found[j] = d
        if len(found) >= 3:
            day_row, day_cols = i, found
            break
    if day_row < 0:
        return []

    out: list[dict[str, Any]] = []
    for i in range(day_row + 1, len(grid)):
        row = grid[i]
        first = row[0] if row else ""
        sec = SECTION_RE.search(first)
        if not sec:
            continue
        start_sec = int(sec.group(1))
        for col, day in day_cols.items():
            if col >= len(row):
                continue
            text = row[col].strip()
            if not text or text in ("-", "&nbsp;"):
                continue
            for c in _cells(text, day):
                c["s1"] = start_sec + c.pop("offset", 0)
                out.append(c)
    return out


def _cells(text: str, day: int) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for line in re.split(r"[\n\r]+|\s{2,}", text):
        line = line.strip()
        if line:
            item = _one(line, day)
            if item:
                out.append(item)
    if not out:
        item = _one(text, day)
        if item:
            out.append(item)
    return out


def _one(text: str, day: int) -> dict[str, Any] | None:
    weeks = WEEK_RE.search(text)
    w1, w2 = (int(weeks.group(1)), int(weeks.group(2))) if weeks else (1, 16)
    parity_match = SINGLE_RE.search(text)
    parity = parity_match.group(1) if parity_match else ""
    clean = WEEK_RE.sub("", text)
    clean = SINGLE_RE.sub("", clean)
    clean = BRACE_RE.sub(" ", clean).strip()

    # 常见格式：课程名 教师 教室 / 课程名@教室 教师 / 课程名 教师@教室
    name, teacher, room = clean, "", ""
    parts = [p for p in re.split(r"[\s@]+", clean) if p]
    if len(parts) >= 3:
        name, teacher, room = parts[0], parts[1], " ".join(parts[2:])
    elif len(parts) == 2:
        name, teacher = parts[0], parts[1]
    if not name:
        return None
    return {
        "name": name,
        "teacher": teacher,
        "room": room,
        "day": day,
        "w1": w1,
        "w2": w2,
        "parity": parity,
        "offset": 0,
    }


def _dedup(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    seen: set[str] = set()
    out: list[dict[str, Any]] = []
    for c in items:
        key = f"{c['name']}|{c['day']}|{c['s1']}|{c['room']}|{c['w1']}|{c['w2']}|{c['parity']}"
        if key not in seen:
            seen.add(key)
            out.append(c)
    return out
