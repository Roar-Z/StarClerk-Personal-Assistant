"""把用户一句话直接写成待办，不走二次确认。"""
from __future__ import annotations

import re
from typing import Any

from .. import access, todos
from ..db import models as meta
from .web_search import ToolError


_PREFIX = re.compile(
    r"^(?:帮我|请)?\s*(?:加个|加一条|新建|创建|记一下|记个|提醒我|加进|加入)?\s*"
    r"(?:待办|日程|清单|todo)?\s*[:：,，]?\s*",
    re.I,
)


def run(text: str, note: str = "") -> dict:
    raw = (text or "").strip()
    if not raw:
        raise ToolError("要写什么待办，说一句就行")
    clean = _PREFIX.sub("", raw).strip() or raw
    if meta.count_todos() >= access.limits_for(access.license.tier())["todos"]:
        raise ToolError("待办清单满了，先删掉几条旧的")

    parsed = todos.parse(clean)
    result = todos.add(
        title=parsed["title"],
        note=note or parsed.get("note", ""),
        due_at=parsed["due_at"],
        end_at=parsed["end_at"],
        priority=parsed["priority"],
        tags=",".join(parsed["tags"]),
        repeat=parsed["repeat"],
        lead_minutes=parsed["lead_minutes"],
    )
    item = result["item"]
    when = "没定时间"
    if item.get("due_at"):
        from datetime import datetime

        when = datetime.fromtimestamp(item["due_at"]).strftime("%m-%d %H:%M")
    summary = f"已加入待办：{item['title']}（{when}）"
    conflicts = result.get("conflicts") or []
    if conflicts:
        summary += "；和已有待办撞时间：" + "、".join(x["title"] for x in conflicts[:3])
    return {"items": [{**item, "source": "待办清单", "text": summary, "answer": summary}]}
