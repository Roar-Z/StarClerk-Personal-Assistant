"""待办提醒子线程：每 30 秒扫一遍到点的待办，走统一的托盘 + SSE 提醒出口。

提醒过一次就打标记，不重复轰炸；日程改了时间会把标记清掉重新算。
"""
from __future__ import annotations

import logging
import threading
from typing import Any

from .. import license, notify
from ..db import sqlite as db

log = logging.getLogger("reminder")


class TodoReminder:
    def __init__(self, interval: int = 30) -> None:
        self.interval = interval
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._stop.clear()
        self._thread = threading.Thread(target=self._loop, name="todo-reminder", daemon=True)
        self._thread.start()
        log.info("待办提醒线程已启动")

    def stop(self, timeout: float = 3) -> None:
        self._stop.set()
        if self._thread:
            self._thread.join(timeout=timeout)
        self._thread = None

    def _loop(self) -> None:
        while not self._stop.is_set():
            try:
                self.tick()
            except Exception as e:  # noqa: BLE001
                log.exception("待办提醒扫描异常：%s", e)
            if self._stop.wait(self.interval):
                break

    def tick(self) -> list[dict[str, Any]]:
        if license.is_guest():
            return []
        now = db.now()
        rows = db.rows(
            "SELECT * FROM todos WHERE done=0 AND reminded=0 AND remind_at IS NOT NULL AND remind_at<=? "
            "ORDER BY remind_at LIMIT 50",
            (now,),
        )
        sent = []
        for r in rows:
            title = "该出门了" if int(r.get("lead_minutes") or 0) > 0 else "待办提醒"
            body = r["title"]
            if r.get("note"):
                body += " · " + str(r["note"])[:60]
            notify.notify(title, body, "warn" if r.get("priority") == "high" else "info")
            db.exec_sql("UPDATE todos SET reminded=1 WHERE id=?", (r["id"],))
            sent.append(r)
        return sent


reminder = TodoReminder()
