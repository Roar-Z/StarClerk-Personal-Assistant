"""SQLite：仅存元数据（会话/消息/任务/记忆索引/设置）。标准库实现，减小打包体积。

写操作用短事务；读用只读连接，WAL 模式支持托盘线程 + 调度线程并发访问。
"""
from __future__ import annotations

import json
import sqlite3
import threading
import time
import uuid
from contextlib import contextmanager
from typing import Any, Iterator

from ..config import settings

_lock = threading.Lock()

SCHEMA = """
CREATE TABLE IF NOT EXISTS sessions(
  id TEXT PRIMARY KEY, title TEXT NOT NULL, created_at REAL NOT NULL, updated_at REAL NOT NULL);
CREATE TABLE IF NOT EXISTS messages(
  id TEXT PRIMARY KEY, session_id TEXT NOT NULL, role TEXT NOT NULL, content TEXT NOT NULL,
  created_at REAL NOT NULL);
CREATE INDEX IF NOT EXISTS idx_messages_session ON messages(session_id, created_at);
CREATE TABLE IF NOT EXISTS tasks(
  id TEXT PRIMARY KEY, name TEXT NOT NULL, kind TEXT NOT NULL, cron_minutes INTEGER NOT NULL DEFAULT 60,
  prompt TEXT NOT NULL, doc_scope TEXT DEFAULT '', enabled INTEGER NOT NULL DEFAULT 1,
  last_run_at REAL, next_run_at REAL, last_result TEXT, created_at REAL NOT NULL);
CREATE TABLE IF NOT EXISTS memories(
  id TEXT PRIMARY KEY, kind TEXT NOT NULL DEFAULT 'fact', content TEXT NOT NULL,
  group_name TEXT NOT NULL DEFAULT '', weight REAL NOT NULL DEFAULT 1.0,
  created_at REAL NOT NULL, updated_at REAL NOT NULL);
CREATE TABLE IF NOT EXISTS kv(k TEXT PRIMARY KEY, v TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS usage(
  id TEXT PRIMARY KEY, scope TEXT NOT NULL, provider TEXT DEFAULT '', model TEXT DEFAULT '',
  prompt_tokens INTEGER NOT NULL DEFAULT 0, completion_tokens INTEGER NOT NULL DEFAULT 0,
  total_tokens INTEGER NOT NULL DEFAULT 0, latency_ms INTEGER NOT NULL DEFAULT 0,
  created_at REAL NOT NULL);
CREATE INDEX IF NOT EXISTS idx_usage_time ON usage(created_at);
CREATE TABLE IF NOT EXISTS errors(
  id TEXT PRIMARY KEY, scope TEXT NOT NULL, message TEXT NOT NULL, created_at REAL NOT NULL);
CREATE INDEX IF NOT EXISTS idx_errors_time ON errors(created_at);
CREATE TABLE IF NOT EXISTS task_logs(
  id TEXT PRIMARY KEY, task_id TEXT NOT NULL, name TEXT NOT NULL, ok INTEGER NOT NULL DEFAULT 1,
  level TEXT NOT NULL DEFAULT 'info', result TEXT NOT NULL DEFAULT '',
  elapsed_ms INTEGER NOT NULL DEFAULT 0, created_at REAL NOT NULL);
CREATE INDEX IF NOT EXISTS idx_task_logs_time ON task_logs(created_at);
CREATE INDEX IF NOT EXISTS idx_task_logs_task ON task_logs(task_id, created_at);
CREATE TABLE IF NOT EXISTS license(
  id INTEGER PRIMARY KEY CHECK (id = 1), tier TEXT NOT NULL DEFAULT 'guest',
  code TEXT NOT NULL DEFAULT '', machine TEXT NOT NULL DEFAULT '',
  activated_at REAL NOT NULL DEFAULT 0, updated_at REAL NOT NULL DEFAULT 0);
"""


@contextmanager
def conn() -> Iterator[sqlite3.Connection]:
    c = sqlite3.connect(settings.db_path, timeout=10)
    c.row_factory = sqlite3.Row
    try:
        yield c
        c.commit()
    finally:
        c.close()


def init_db() -> None:
    with _lock, conn() as c:
        c.executescript(SCHEMA)
        c.execute("PRAGMA journal_mode=WAL")
        _add_columns(c)


def _add_columns(c: sqlite3.Connection) -> None:
    """老版本的库缺字段时补上，省得用户升级还得删数据。"""
    for table, column, ddl in (
        ("memories", "group_name", "TEXT NOT NULL DEFAULT ''"),
        ("tasks", "workspace", "TEXT NOT NULL DEFAULT ''"),
    ):
        have = {r["name"] for r in c.execute(f"PRAGMA table_info({table})")}
        if column not in have:
            c.execute(f"ALTER TABLE {table} ADD COLUMN {column} {ddl}")


def rows(sql: str, args: tuple = ()) -> list[dict[str, Any]]:
    with conn() as c:
        return [dict(r) for r in c.execute(sql, args).fetchall()]


def row(sql: str, args: tuple = ()) -> dict[str, Any] | None:
    r = rows(sql, args)
    return r[0] if r else None


def exec_sql(sql: str, args: tuple = ()) -> None:
    with _lock, conn() as c:
        c.execute(sql, args)


def exec_rowcount(sql: str, args: tuple = ()) -> int:
    """需要判断“是否抢到”时用：返回受影响行数（如任务抢占）。"""
    with _lock, conn() as c:
        cur = c.execute(sql, args)
        return cur.rowcount


def new_id() -> str:
    return uuid.uuid4().hex[:12]


def now() -> float:
    return time.time()


def json_dump(obj: Any) -> str:
    return json.dumps(obj, ensure_ascii=False)
