"""待办梯度提醒：提前 30 分钟、临近（出门预留/10 分钟）、到点，一共三次。

每个阶段只发一次；点「已确认」就停掉这条待办后面所有阶段，
点「关闭」只记当前阶段关了，后面的照发；没人点 10 分钟后前端自动收起，也不影响后面。
"""
from __future__ import annotations

import logging
import threading
from datetime import datetime
from typing import Any

from .. import license
from ..db import sqlite as db
from ..notify import notifier

log = logging.getLogger("reminder")

STAGE_LABELS = {1: "提前半小时", 2: "快到时间了", 3: "到点了"}
STAGE_LEVELS = {1: "info", 2: "warn", 3: "urgent"}


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

    @staticmethod
    def _stages(lead: int) -> list[tuple[int, float]]:
        """返回阶段和提前多少分钟；出门预留填了就用它当第二阶段。"""
        second = lead if lead and 0 < lead < 30 else 10
        return [(1, 30.0), (2, float(second)), (3, 0.0)]

    def tick(self) -> list[dict[str, Any]]:
        if license.is_guest():
            return []
        now = db.now()
        rows = db.rows(
            "SELECT * FROM todos WHERE done=0 AND ack=0 AND due_at IS NOT NULL "
            "AND due_at<=? ORDER BY due_at LIMIT 100",
            (now + 31 * 60,),
        )
        sent = []
        for r in rows:
            due = float(r["due_at"])
            for stage, minutes in self._stages(int(r.get("lead_minutes") or 0)):
                at = due - minutes * 60
                if at > now:
                    continue
                if at < float(r.get("created_at") or 0) - 30:
                    continue  # 新建时早就过了这个点，别补发一堆过期提醒
                added = db.exec_rowcount(
                    "INSERT OR IGNORE INTO todo_reminders(todo_id, stage, sent_at) VALUES(?,?,?)",
                    (r["id"], stage, now),
                )
                if not added:
                    continue
                when = datetime.fromtimestamp(due).strftime("%Y年%m月%d日 %H:%M:%S")
                body = f"{r['title']} · {when}"
                if r.get("note"):
                    body += f" · {str(r['note'])[:60]}"
                notifier.todo_reminder(
                    {
                        "event_id": f"{r['id']}-{stage}",
                        "todo_id": r["id"],
                        "stage": stage,
                        "title": STAGE_LABELS[stage],
                        "body": body,
                        "level": STAGE_LEVELS[stage],
                        "due_at": due,
                    }
                )
                sent.append({"id": r["id"], "stage": stage})
        return sent


reminder = TodoReminder()
