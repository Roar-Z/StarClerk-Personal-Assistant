"""领域模型 + 仓储函数（不用 ORM，直接 SQL，便于 PyInstaller 打包）。"""
from __future__ import annotations

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
def add_memory(content: str, kind: str = "fact", weight: float = 1.0) -> dict[str, Any]:
    mid, t = db.new_id(), db.now()
    db.exec_sql(
        "INSERT INTO memories(id,kind,content,weight,created_at,updated_at) VALUES(?,?,?,?,?,?)",
        (mid, kind, content, weight, t, t),
    )
    return {"id": mid, "kind": kind, "content": content, "weight": weight}


def list_memories(limit: int = 200) -> list[dict[str, Any]]:
    return db.rows("SELECT * FROM memories ORDER BY updated_at DESC LIMIT ?", (limit,))


def delete_memory(mid: str) -> None:
    db.exec_sql("DELETE FROM memories WHERE id=?", (mid,))


# ---------------- 巡检任务 ----------------
def create_task(
    name: str,
    prompt: str,
    kind: str = "patrol",
    cron_minutes: int = 60,
    doc_scope: str = "",
) -> dict[str, Any]:
    tid, t = db.new_id(), db.now()
    db.exec_sql(
        """INSERT INTO tasks(id,name,kind,cron_minutes,prompt,doc_scope,enabled,next_run_at,created_at)
           VALUES(?,?,?,?,?,?,1,?,?)""",
        (tid, name, kind, cron_minutes, prompt, doc_scope, t + cron_minutes * 60, t),
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


def claim_task(tid: str, ts: float) -> bool:
    """抢占一次执行权：先把 next_run 推到下一个周期，避免 tick 重复触发/并发执行。"""
    task = get_task(tid) or {}
    nxt = ts + max(1, int(task.get("cron_minutes") or 60)) * 60
    return db.exec_rowcount(
        "UPDATE tasks SET last_run_at=?, next_run_at=?, last_result=? WHERE id=? AND enabled=1",
        (ts, nxt, "运行中…", tid),
    ) > 0


def finish_task(tid: str, result: str) -> None:
    db.exec_sql("UPDATE tasks SET last_result=? WHERE id=?", (result[:4000], tid))


def set_task_enabled(tid: str, enabled: bool) -> None:
    db.exec_sql("UPDATE tasks SET enabled=? WHERE id=?", (1 if enabled else 0, tid))


def delete_task(tid: str) -> None:
    db.exec_sql("DELETE FROM tasks WHERE id=?", (tid,))


def plan_info() -> dict[str, Any]:
    """免费/Pro 托管任务额度：MVP 用 kv 存套餐，接口可切换，不需要重启。"""
    from ..config import settings

    plan = str(kv_get("plan", settings.plan)).lower()
    limit = settings.pro_task_limit if plan == "pro" else settings.free_task_limit
    used = len(list_tasks())
    return {
        "plan": plan,
        "is_pro": plan == "pro",
        "limit": limit,
        "used": used,
        "remaining": max(0, limit - used),
    }


def set_plan(plan: str) -> dict[str, Any]:
    kv_set("plan", "pro" if plan == "pro" else "free")
    return plan_info()


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
