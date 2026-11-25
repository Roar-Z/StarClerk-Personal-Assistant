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


def search_sessions(q: str, limit: int = 50) -> list[dict[str, Any]]:
    """标题和消息内容一起搜，命中的会话按最近更新排。"""
    like = f"%{q}%"
    return db.rows(
        """SELECT s.id, s.title, s.updated_at FROM sessions s
           WHERE s.title LIKE ?
              OR EXISTS(SELECT 1 FROM messages m WHERE m.session_id=s.id AND m.content LIKE ?)
           ORDER BY s.updated_at DESC LIMIT ?""",
        (like, like, limit),
    )


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


def set_task_value(tid: str, value: str) -> None:
    """网页监控存上一次的摘要值，只存一行，不单独建表。"""
    db.exec_sql("UPDATE tasks SET last_value=? WHERE id=?", (value, tid))


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
    url: str = "",
) -> dict[str, Any]:
    tid, t = db.new_id(), db.now()
    db.exec_sql(
        """INSERT INTO tasks(id,name,kind,cron_minutes,prompt,doc_scope,workspace,url,enabled,next_run_at,created_at)
           VALUES(?,?,?,?,?,?,?,?,1,?,?)""",
        (tid, name, kind, cron_minutes, prompt, doc_scope, workspace, url, t + cron_minutes * 60, t),
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
        "is_guest": tier == "guest",
        "limit": limit,
        "used": used,
        "remaining": max(0, limit - used),
    }


# ---------------- 本地授权状态 ----------------
def license_get() -> dict[str, Any] | None:
    return db.row("SELECT * FROM license WHERE id=1")


def license_set(tier: str, code: str, machine: str) -> None:
    # 从旧迁移包导入时可能还是 pro，落到库里统一算已登录
    if str(tier).lower() == "pro":
        tier = "free"
    t = db.now()
    db.exec_sql(
        """INSERT INTO license(id,tier,code,machine,activated_at,updated_at) VALUES(1,?,?,?,?,?)
           ON CONFLICT(id) DO UPDATE SET tier=excluded.tier, code=excluded.code,
           machine=excluded.machine, activated_at=excluded.activated_at, updated_at=excluded.updated_at""",
        (tier, code, machine, t, t),
    )


def license_clear(machine: str = "") -> None:
    """退出登录也要留一行，否则「库里没有」会被当成新机器去读 json 备份。"""
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
    session_id: str = "",
    task_id: str = "",
) -> None:
    """每次模型调用落一行，便于按天/按场景统计（重启不丢）。"""
    db.exec_sql(
        """INSERT INTO usage(id,scope,provider,model,prompt_tokens,completion_tokens,total_tokens,
                             latency_ms,session_id,task_id,created_at)
           VALUES(?,?,?,?,?,?,?,?,?,?,?)""",
        (
            db.new_id(),
            scope,
            provider,
            model,
            int(usage.get("prompt_tokens", 0)),
            int(usage.get("completion_tokens", 0)),
            int(usage.get("total_tokens", 0)),
            int(latency_ms),
            session_id,
            task_id,
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


# ---------------- 笔记 ----------------
def _note_rows(where: str, args: tuple, limit: int) -> list[dict[str, Any]]:
    return db.rows(
        f"SELECT * FROM notes {where} ORDER BY pinned DESC, updated_at DESC LIMIT ?", args + (limit,)
    )


def create_note(title: str, body: str = "", category: str = "", tags: str = "") -> dict[str, Any]:
    nid, t = db.new_id(), db.now()
    db.exec_sql(
        "INSERT INTO notes(id,title,body,category,tags,pinned,created_at,updated_at) VALUES(?,?,?,?,?,0,?,?)",
        (nid, title, body, category, tags, t, t),
    )
    return get_note(nid) or {}


def get_note(nid: str) -> dict[str, Any] | None:
    return db.row("SELECT * FROM notes WHERE id=?", (nid,))


def update_note(nid: str, **fields: Any) -> dict[str, Any] | None:
    allow = ("title", "body", "category", "tags", "pinned")
    used = {k: v for k, v in fields.items() if k in allow and v is not None}
    if used:
        cols = ", ".join(f"{k}=?" for k in used)
        db.exec_sql(
            f"UPDATE notes SET {cols}, updated_at=? WHERE id=?",
            tuple(used.values()) + (db.now(), nid),
        )
    return get_note(nid)


def delete_note(nid: str) -> None:
    db.exec_sql("DELETE FROM notes WHERE id=?", (nid,))


def find_notes(q: str = "", category: str = "", tag: str = "", limit: int = 200) -> list[dict[str, Any]]:
    where, args = [], []
    if q:
        where.append("(title LIKE ? OR body LIKE ? OR tags LIKE ?)")
        args += [f"%{q}%"] * 3
    if category:
        where.append("category=?")
        args.append(category)
    if tag:
        where.append("tags LIKE ?")
        args.append(f"%{tag}%")
    clause = ("WHERE " + " AND ".join(where)) if where else ""
    return _note_rows(clause, tuple(args), limit)


def note_categories() -> list[dict[str, Any]]:
    return db.rows(
        "SELECT category, COUNT(*) n FROM notes GROUP BY category ORDER BY n DESC"
    )


def count_notes() -> int:
    return int((db.row("SELECT COUNT(*) n FROM notes") or {}).get("n") or 0)


# ---------------- 技能模板 ----------------
BUILTIN_SKILLS: tuple[tuple[str, str, str], ...] = (
    (
        "刷题讲解",
        "学习",
        "你是一名算法助教。看下面这道题，先讲清题意和边界条件，再给一份能跑的 Python 解法，"
        "最后说时间复杂度和容易踩的坑。别直接堆代码，一步步来。\n\n题目：{input}",
    ),
    (
        "作文批改",
        "写作",
        "你是大学写作课的助教。读下面这篇稿子，从结构、论证、语句三方面挑毛病，"
        "每条都给具体的改法，最后给一段改写后的开头。语气别太客气。\n\n原文：{input}",
    ),
    (
        "代码审查",
        "编程",
        "你看一段代码。先说它想干什么，再列出真会影响运行或维护的问题，按严重程度排序，"
        "每条给出行号和改法。风格上的小事放最后，别写成清单作文。\n\n代码：{input}",
    ),
    (
        "学习计划",
        "学习",
        "按我给的科目和可用时间排一份复习计划。明确每天做什么、做多久，留出补漏的时间，"
        "别排太满。输出用表格。\n\n情况：{input}",
    ),
    (
        "翻译润色",
        "语言",
        "把下面的内容翻成自然的中文（或英文，看内容），保留术语原样，再给一版更口语的改法。\n\n原文：{input}",
    ),
    (
        "面试问答",
        "求职",
        "你是一名技术面试官。针对下面这个岗位，出 5 个会追问到底的问题，每个都写一句"
        "「面试官想看什么」。然后用一段话告诉我回答这类问题的结构。\n\n岗位：{input}",
    ),
)


def seed_skills() -> None:
    """内置模板只插一次，用户删掉后不再自动补回来。"""
    if kv_get("skills_seeded"):
        return
    t = db.now()
    for name, cat, body in BUILTIN_SKILLS:
        db.exec_sql(
            "INSERT INTO skills(id,name,category,body,builtin,use_count,created_at,updated_at)"
            " VALUES(?,?,?,?,1,0,?,?)",
            (db.new_id(), name, cat, body, t, t),
        )
    kv_set("skills_seeded", True)


def list_skills(category: str = "") -> list[dict[str, Any]]:
    if category:
        return db.rows(
            "SELECT * FROM skills WHERE category=? ORDER BY builtin DESC, updated_at DESC", (category,)
        )
    return db.rows("SELECT * FROM skills ORDER BY builtin DESC, updated_at DESC")


def get_skill(sid: str) -> dict[str, Any] | None:
    return db.row("SELECT * FROM skills WHERE id=?", (sid,))


def create_skill(name: str, category: str, body: str) -> dict[str, Any]:
    sid, t = db.new_id(), db.now()
    db.exec_sql(
        "INSERT INTO skills(id,name,category,body,builtin,use_count,created_at,updated_at)"
        " VALUES(?,?,?,?,0,0,?,?)",
        (sid, name, category or "通用", body, t, t),
    )
    return get_skill(sid) or {}


def update_skill(sid: str, **fields: Any) -> dict[str, Any] | None:
    allow = ("name", "category", "body")
    used = {k: v for k, v in fields.items() if k in allow and v is not None}
    if used:
        cols = ", ".join(f"{k}=?" for k in used)
        db.exec_sql(
            f"UPDATE skills SET {cols}, updated_at=? WHERE id=?",
            tuple(used.values()) + (db.now(), sid),
        )
    return get_skill(sid)


def delete_skill(sid: str) -> None:
    """内置模板允许删，但不给改内置标记，删了就是自己的事了。"""
    db.exec_sql("DELETE FROM skills WHERE id=?", (sid,))


def bump_skill(sid: str) -> None:
    db.exec_sql("UPDATE skills SET use_count=use_count+1 WHERE id=?", (sid,))


def count_skills() -> int:
    return int((db.row("SELECT COUNT(*) n FROM skills") or {}).get("n") or 0)


# ---------------- 更细的用量 ----------------
def usage_by_session(days: int = 30, limit: int = 20) -> list[dict[str, Any]]:
    return db.rows(
        """SELECT u.session_id sid, COALESCE(s.title,'') title, COUNT(*) calls,
                  COALESCE(SUM(u.total_tokens),0) total_tokens
           FROM usage u LEFT JOIN sessions s ON s.id=u.session_id
           WHERE u.created_at>=? AND u.session_id<>''
           GROUP BY u.session_id ORDER BY total_tokens DESC LIMIT ?""",
        (db.now() - days * 86400, limit),
    )


def usage_by_task(days: int = 30) -> list[dict[str, Any]]:
    return db.rows(
        """SELECT u.task_id tid, COALESCE(t.name,'') name, COUNT(*) calls,
                  COALESCE(SUM(u.total_tokens),0) total_tokens
           FROM usage u LEFT JOIN tasks t ON t.id=u.task_id
           WHERE u.created_at>=? AND u.task_id<>''
           GROUP BY u.task_id ORDER BY total_tokens DESC LIMIT 20""",
        (db.now() - days * 86400,),
    )


def usage_alerts(days: int = 1) -> dict[str, Any]:
    """当天用量超过阈值就报一声，阈值存在 kv 里，默认 10 万 token。"""
    since = db.now() - days * 86400
    used = int((db.row("SELECT COALESCE(SUM(total_tokens),0) n FROM usage WHERE created_at>=?", (since,)) or {}).get("n") or 0)
    cap = int(kv_get("usage_alert_limit", 100000) or 100000)
    return {"days": days, "used": used, "limit": cap, "over": used >= cap}


# ---------------- 画像 ----------------
def memory_profile() -> dict[str, Any]:
    """把记忆按 kind 归一堆，前端拿去画卡片，不做花哨的推断。"""
    kinds = db.rows("SELECT kind, COUNT(*) n FROM memories GROUP BY kind ORDER BY n DESC")
    groups = db.rows(
        "SELECT group_name name, COUNT(*) n FROM memories WHERE group_name<>'' GROUP BY group_name ORDER BY n DESC"
    )
    recent = db.rows("SELECT content, kind, group_name, updated_at FROM memories ORDER BY updated_at DESC LIMIT 12")
    return {"kinds": kinds, "groups": groups, "recent": recent, "total": count_memories()}


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
