"""待办与日程：增删改、自然语言解析、冲突检查、CSV/ICS 导出。

完成重复事件时直接生成下一条，不用用户再录一遍。
"""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import Response
from pydantic import BaseModel, Field

from .. import access, todos
from ..db import models as meta
from ..db import sqlite as db

router = APIRouter(prefix="/todos", tags=["todos"])


class TodoIn(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    note: str = ""
    due_at: float | None = None
    end_at: float | None = None
    priority: str = "normal"
    tags: str = ""
    repeat: str = "once"
    lead_minutes: int = 0


class ParseIn(BaseModel):
    text: str = Field(min_length=1, max_length=300)


def _row_out(r: dict[str, Any]) -> dict[str, Any]:
    return r


@router.get("", summary="待办列表")
def list_todos(done: str = "0", tag: str = "", q: str = "", limit: int = 200):
    sql = "SELECT * FROM todos WHERE 1=1"
    args: list[Any] = []
    if done in ("0", "1"):
        sql += " AND done=?"
        args.append(int(done))
    if tag:
        sql += " AND tags LIKE ?"
        args.append(f"%{tag}%")
    if q:
        sql += " AND (title LIKE ? OR note LIKE ?)"
        args.extend([f"%{q}%", f"%{q}%"])
    sql += " ORDER BY done, due_at IS NULL, due_at LIMIT ?"
    args.append(max(1, min(limit, 500)))
    return [_row_out(r) for r in db.rows(sql, tuple(args))]


@router.post("/parse", summary="一句话解析成待办")
def parse(body: ParseIn):
    return todos.parse(body.text)


@router.get("/conflicts", summary="时间冲突检查")
def check_conflicts(due_at: float, end_at: float, exclude: str = ""):
    return {"items": todos.conflicts(due_at, end_at, exclude)}


@router.post("", summary="新建待办")
def create(body: TodoIn):
    access.check_limit("todos", meta.count_todos())
    if body.priority not in ("low", "normal", "high"):
        raise HTTPException(400, "priority 只能是 low / normal / high")
    if body.repeat not in ("once", "daily", "weekly", "monthly"):
        raise HTTPException(400, "repeat 只能是 once / daily / weekly / monthly")
    result = todos.add(
        title=body.title,
        note=body.note,
        due_at=body.due_at,
        end_at=body.end_at,
        priority=body.priority,
        tags=body.tags,
        repeat=body.repeat,
        lead_minutes=body.lead_minutes,
    )
    return {"item": _row_out(result["item"]), **({"conflicts": result["conflicts"]} if result.get("conflicts") else {})}


@router.patch("/{tid}", summary="改待办")
def update(tid: str, body: TodoIn):
    old = db.row("SELECT * FROM todos WHERE id=?", (tid,))
    if not old:
        raise HTTPException(404, "没找到这条待办")
    due = body.due_at
    end = body.end_at or (due + 1800 if due else None)
    remind = due - max(0, body.lead_minutes) * 60 if due else None
    db.exec_sql(
        "UPDATE todos SET title=?,note=?,due_at=?,end_at=?,priority=?,tags=?,repeat=?,lead_minutes=?,"
        "remind_at=?,reminded=0,updated_at=? WHERE id=?",
        (
            body.title.strip(),
            body.note.strip(),
            due,
            end,
            body.priority,
            body.tags.strip(),
            body.repeat,
            max(0, body.lead_minutes),
            remind,
            db.now(),
            tid,
        ),
    )
    row = db.row("SELECT * FROM todos WHERE id=?", (tid,)) or {}
    return {"item": _row_out(row)}


@router.post("/{tid}/done", summary="完成待办（重复的自动生成下一条）")
def finish(tid: str):
    old = db.row("SELECT * FROM todos WHERE id=?", (tid,))
    if not old:
        raise HTTPException(404, "没找到这条待办")
    t = db.now()
    db.exec_sql("UPDATE todos SET done=1, done_at=?, updated_at=? WHERE id=?", (t, t, tid))
    nxt = todos.next_due(old)
    new_item = None
    if nxt:
        span = float(old.get("end_at") or 0) - float(old.get("due_at") or 0)
        nid = db.new_id()
        lead = int(old.get("lead_minutes") or 0)
        db.exec_sql(
            "INSERT INTO todos(id,title,note,due_at,end_at,priority,tags,repeat,lead_minutes,remind_at,"
            "reminded,done,done_at,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?,?,0,0,NULL,?,?)",
            (
                nid,
                old["title"],
                old.get("note") or "",
                nxt,
                nxt + (span if span > 0 else 1800),
                old.get("priority") or "normal",
                old.get("tags") or "",
                old.get("repeat") or "once",
                lead,
                nxt - lead * 60,
                t,
                t,
            ),
        )
        new_item = db.row("SELECT * FROM todos WHERE id=?", (nid,))
    return {"ok": True, "next": new_item}


@router.delete("/{tid}", summary="删待办")
def remove(tid: str):
    db.exec_sql("DELETE FROM todos WHERE id=?", (tid,))
    return {"ok": True}


@router.get("/export", summary="导出 CSV / iCal")
def export(fmt: str = "csv", done: str = "all"):
    sql = "SELECT * FROM todos WHERE 1=1"
    args: tuple = ()
    if done in ("0", "1"):
        sql += " AND done=?"
        args = (int(done),)
    sql += " ORDER BY due_at IS NULL, due_at"
    rows = db.rows(sql, args)
    if fmt == "ics":
        return Response(
            todos.to_ics(rows),
            media_type="text/calendar; charset=utf-8",
            headers={"Content-Disposition": 'attachment; filename="starclerk-todos.ics"'},
        )
    return Response(
        todos.to_csv(rows),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": 'attachment; filename="starclerk-todos.csv"'},
    )
