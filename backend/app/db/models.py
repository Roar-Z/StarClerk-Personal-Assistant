"""领域模型 + 仓储函数（不用 ORM，直接 SQL，便于 PyInstaller 打包）。"""
from __future__ import annotations

import random
from typing import Any, Literal

from . import sqlite as db

Role = Literal["user", "assistant", "system"]


# ---------------- 会话 ----------------
def create_session(title: str = "新对话") -> dict[str, Any]:
    sid, t = db.new_id(), db.now()
    db.exec_sql(
        "INSERT INTO sessions(id,title,created_at,updated_at) VALUES(?,?,?,?)",
        (sid, title, t, t),
    )
    return {"id": sid, "title": title, "created_at": t, "updated_at": t}


def list_sessions(limit: int = 50) -> list[dict[str, Any]]:
    return db.rows("SELECT * FROM sessions ORDER BY updated_at DESC LIMIT ?", (limit,))


def get_session(session_id: str) -> dict[str, Any] | None:
    return db.row("SELECT * FROM sessions WHERE id=?", (session_id,))


def add_message(session_id: str, role: Role, content: str) -> dict[str, Any]:
    mid, t = db.new_id(), db.now()
    db.exec_sql(
        "INSERT INTO messages(id,session_id,role,content,created_at) VALUES(?,?,?,?,?)",
        (mid, session_id, role, content, t),
    )
    db.exec_sql("UPDATE sessions SET updated_at=? WHERE id=?", (t, session_id))
    return {"id": mid, "session_id": session_id, "role": role, "content": content, "created_at": t}


def history(session_id: str, limit: int = 12) -> list[dict[str, str]]:
    rs = db.rows(
        "SELECT role,content FROM messages WHERE session_id=? ORDER BY created_at DESC LIMIT ?",
        (session_id, limit),
    )
    return [{"role": r["role"], "content": r["content"]} for r in reversed(rs)]


def rename_session(session_id: str, title: str) -> None:
    db.exec_sql("UPDATE sessions SET title=? WHERE id=?", (title[:60], session_id))


def delete_session(session_id: str) -> None:
    db.exec_sql("DELETE FROM messages WHERE session_id=?", (session_id,))
    db.exec_sql("DELETE FROM sessions WHERE id=?", (session_id,))


# ---------------- 记忆元数据 ----------------
def add_memory(
    content: str, kind: str = "fact", weight: float = 1.0, group_name: str = ""
) -> dict[str, Any]:
    mid, t = db.new_id(), db.now()
    db.exec_sql(
        """INSERT INTO memories(id,kind,content,group_name,weight,created_at,updated_at)
           VALUES(?,?,?,?,?,?,?)""",
        (mid, kind, content, group_name, weight, t, t),
    )
    return {"id": mid, "kind": kind, "content": content, "group_name": group_name, "weight": weight}


def list_memories(limit: int = 200, group_name: str = "") -> list[dict[str, Any]]:
    if group_name:
        return db.rows(
            "SELECT * FROM memories WHERE group_name=? ORDER BY updated_at DESC LIMIT ?",
            (group_name, limit),
        )
    return db.rows("SELECT * FROM memories ORDER BY updated_at DESC LIMIT ?", (limit,))


def count_memories(group_name: str = "") -> int:
    sql = "SELECT COUNT(*) n FROM memories"
    args: tuple = ()
    if group_name:
        sql += " WHERE group_name=?"
        args = (group_name,)
    r = db.row(sql, args)
    return int(r["n"]) if r else 0


def memory_groups() -> list[dict[str, Any]]:
    return db.rows(
        """SELECT group_name name, COUNT(*) n FROM memories
           GROUP BY group_name ORDER BY n DESC"""
    )


def set_memory_group(mid: str, group_name: str) -> None:
    db.exec_sql(
        "UPDATE memories SET group_name=?, updated_at=? WHERE id=?",
        (group_name[:40], db.now(), mid),
    )


def delete_memory(mid: str) -> None:
    db.exec_sql("DELETE FROM memories WHERE id=?", (mid,))


# ---------------- 巡检任务 ----------------
def create_task(
    name: str,
    prompt: str,
    kind: str = "patrol",
    cron_minutes: int = 60,
    doc_scope: str = "",
    workspace: str = "",
) -> dict[str, Any]:
    tid, t = db.new_id(), db.now()
    db.exec_sql(
        """INSERT INTO tasks(id,name,kind,cron_minutes,prompt,doc_scope,workspace,enabled,next_run_at,created_at)
           VALUES(?,?,?,?,?,?,?,1,?,?)""",
        (tid, name, kind, cron_minutes, prompt, doc_scope, workspace, t + cron_minutes * 60, t),
    )
    return get_task(tid) or {}


def get_task(tid: str) -> dict[str, Any] | None:
    return db.row("SELECT * FROM tasks WHERE id=?", (tid,))


def list_tasks() -> list[dict[str, Any]]:
    return db.rows("SELECT * FROM tasks ORDER BY created_at DESC")


def due_tasks(ts: float) -> list[dict[str, Any]]:
    return db.rows(
        "SELECT * FROM tasks WHERE enabled=1 AND (next_run_at IS NULL OR next_run_at<=?)", (ts,)
    )


def claim_task(tid: str, ts: float, scale: float = 1.0) -> bool:
    """抢占一次执行权：先把 next_run 推到下一个周期，避免 tick 重复触发/并发执行。

    scale 是性能模式的倍数，jitter 让几条任务的到期时间错开几十秒。
    """
    task = get_task(tid) or {}
    gap = max(1, int(task.get("cron_minutes") or 60)) * 60 * max(0.5, float(scale))
    nxt = ts + gap + random.uniform(0, 15)
    return db.exec_rowcount(
        "UPDATE tasks SET last_run_at=?, next_run_at=?, last_result=? WHERE id=? AND enabled=1",
        (ts, nxt, "运行中…", tid),
    ) > 0


def restore_next_run(tid: str, ts: float) -> None:
    """排队没排上时把时间调回来，下一轮还能再捡起来。"""
    db.exec_sql("UPDATE tasks SET next_run_at=? WHERE id=?", (ts, tid))


def finish_task(tid: str, result: str) -> None:
    db.exec_sql("UPDATE tasks SET last_result=? WHERE id=?", (result[:4000], tid))


def set_task_enabled(tid: str, enabled: bool) -> None:
    db.exec_sql("UPDATE tasks SET enabled=? WHERE id=?", (1 if enabled else 0, tid))


def delete_task(tid: str) -> None:
    db.exec_sql("DELETE FROM tasks WHERE id=?", (tid,))


def plan_info() -> dict[str, Any]:
    """档位和任务额度：档位从本地授权来，额度表在 access 里。"""
    from .. import access, license

    tier = license.tier()
    limit = access.limits_for(tier)["tasks"]
    used = len(list_tasks())
    return {
        "plan": tier,
        "tier": tier,
        "is_pro": tier == "pro",
        "is_guest": tier == "guest",
        "limit": limit,
        "used": used,
        "remaining": max(0, limit - used),
    }


# ---------------- 本地授权状态 ----------------
def license_get() -> dict[str, Any] | None:
    return db.row("SELECT * FROM license WHERE id=1")


def license_set(tier: str, code: str, machine: str) -> None:
    t = db.now()
    db.exec_sql(
        """INSERT INTO license(id,tier,code,machine,activated_at,updated_at) VALUES(1,?,?,?,?,?)
           ON CONFLICT(id) DO UPDATE SET tier=excluded.tier, code=excluded.code,
           machine=excluded.machine, activated_at=excluded.activated_at, updated_at=excluded.updated_at""",
        (tier, code, machine, t, t),
    )


def license_clear(machine: str = "") -> None:
    """退回游客也要留一行，否则「库里没有」会被当成新机器去读 json 备份。"""
    t = db.now()
    db.exec_sql(
        """INSERT INTO license(id,tier,code,machine,activated_at,updated_at) VALUES(1,'guest','',?,0,?)
           ON CONFLICT(id) DO UPDATE SET tier='guest', code='', activated_at=0, updated_at=?""",
        (machine, t, t),
    )


# ---------------- 巡检历史日志 ----------------
def add_task_log(
    task_id: str,
    name: str,
    ok: bool,
    level: str,
    result: str,
    elapsed_ms: int = 0,
    created_at: float | None = None,
) -> dict[str, Any]:
    lid, t = db.new_id(), created_at or db.now()
    db.exec_sql(
        """INSERT INTO task_logs(id,task_id,name,ok,level,result,elapsed_ms,created_at)
           VALUES(?,?,?,?,?,?,?,?)""",
        (lid, task_id, name[:60], 1 if ok else 0, level, result[:4000], int(elapsed_ms), t),
    )
    return {"id": lid, "task_id": task_id, "name": name, "ok": bool(ok), "level": level,
            "result": result, "elapsed_ms": int(elapsed_ms), "created_at": t}


def list_task_logs(task_id: str = "", limit: int = 50) -> list[dict[str, Any]]:
    if task_id:
        return db.rows(
            "SELECT * FROM task_logs WHERE task_id=? ORDER BY created_at DESC LIMIT ?",
            (task_id, limit),
        )
    return db.rows("SELECT * FROM task_logs ORDER BY created_at DESC LIMIT ?", (limit,))


def count_task_logs(task_id: str = "") -> int:
    sql = "SELECT COUNT(*) n FROM task_logs"
    args: tuple = ()
    if task_id:
        sql += " WHERE task_id=?"
        args = (task_id,)
    r = db.row(sql, args)
    return int(r["n"]) if r else 0


def prune_task_logs(keep: int = 2000) -> None:
    """日志只留最近若干条，本地 SQLite 别无限长。"""
    db.exec_sql(
        "DELETE FROM task_logs WHERE id NOT IN (SELECT id FROM task_logs ORDER BY created_at DESC LIMIT ?)",
        (max(100, keep),),
    )


# ---------------- Token 用量 ----------------
def add_usage(
    scope: str,
    provider: str,
    model: str,
    usage: dict[str, int],
    latency_ms: int = 0,
) -> None:
    """每次模型调用落一行，便于按天/按场景统计（重启不丢）。"""
    db.exec_sql(
        """INSERT INTO usage(id,scope,provider,model,prompt_tokens,completion_tokens,total_tokens,latency_ms,created_at)
           VALUES(?,?,?,?,?,?,?,?,?)""",
        (
            db.new_id(),
            scope,
            provider,
            model,
            int(usage.get("prompt_tokens", 0)),
            int(usage.get("completion_tokens", 0)),
            int(usage.get("total_tokens", 0)),
            int(latency_ms),
            db.now(),
        ),
    )


def usage_summary(days: int = 7) -> dict[str, Any]:
    since = db.now() - days * 86400
    total = db.row(
        """SELECT COUNT(*) calls, COALESCE(SUM(prompt_tokens),0) prompt_tokens,
                  COALESCE(SUM(completion_tokens),0) completion_tokens,
                  COALESCE(SUM(total_tokens),0) total_tokens
           FROM usage WHERE created_at>=?""",
        (since,),
    ) or {}
    by_scope = db.rows(
        """SELECT scope, COUNT(*) calls, SUM(total_tokens) total_tokens
           FROM usage WHERE created_at>=? GROUP BY scope ORDER BY total_tokens DESC""",
        (since,),
    )
    by_model = db.rows(
        """SELECT provider, model, COUNT(*) calls, SUM(total_tokens) total_tokens
           FROM usage WHERE created_at>=? GROUP BY provider, model ORDER BY total_tokens DESC""",
        (since,),
    )
    daily = db.rows(
        """SELECT date(created_at,'unixepoch','localtime') day, COUNT(*) calls,
                  SUM(total_tokens) total_tokens
           FROM usage WHERE created_at>=? GROUP BY day ORDER BY day""",
        (since,),
    )
    return {"days": days, "totals": total, "by_scope": by_scope, "by_model": by_model, "daily": daily}


# ---------------- 异常日志 ----------------
def add_error(scope: str, message: str) -> None:
    db.exec_sql(
        "INSERT INTO errors(id,scope,message,created_at) VALUES(?,?,?,?)",
        (db.new_id(), scope, message[:2000], db.now()),
    )


def list_errors(limit: int = 30) -> list[dict[str, Any]]:
    return db.rows("SELECT * FROM errors ORDER BY created_at DESC LIMIT ?", (limit,))


def count_errors(since: float) -> int:
    r = db.row("SELECT COUNT(*) n FROM errors WHERE created_at>=?", (since,))
    return int(r["n"]) if r else 0


# ---------------- KV 设置 ----------------
def kv_get(key: str, default: Any = None) -> Any:
    import json

    r = db.row("SELECT v FROM kv WHERE k=?", (key,))
    return json.loads(r["v"]) if r else default


def kv_set(key: str, value: Any) -> None:
    db.exec_sql(
        "INSERT INTO kv(k,v) VALUES(?,?) ON CONFLICT(k) DO UPDATE SET v=excluded.v",
        (key, db.json_dump(value)),
    )
