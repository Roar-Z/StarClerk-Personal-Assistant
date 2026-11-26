"""学习通作业同步：每天 12:40、19:00、22:00 各查一次，其余时间不发请求。

首次扫码登录成功会立刻查一次（由 api/study.py 直接调 sync_now）。
总开关关着就只记日志，不发网络请求。
"""
from __future__ import annotations

import logging
import threading
import time
from datetime import datetime
from typing import Any

from .. import license, notify
from ..study import chaoxing, store

log = logging.getLogger("study.sync")

SLOTS = ((12, 40), (19, 0), (22, 0))  # 每天固定三个点
KEY_DONE = "study.slot_done"          # 记录当天哪几个点已经跑过


class StudySync:
    def __init__(self, interval: int = 30) -> None:
        self.interval = interval
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._stop.clear()
        self._thread = threading.Thread(target=self._loop, name="study-sync", daemon=True)
        self._thread.start()
        log.info("学习通定时线程已启动（12:40 / 19:00 / 22:00）")

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
                log.exception("学习通定时扫描异常：%s", e)
            if self._stop.wait(self.interval):
                break

    def tick(self) -> list[dict[str, Any]]:
        """没到点、没开开关、过期的都直接返回，不发请求。"""
        if not store.enabled():
            return []
        now = time.time()
        local = datetime.fromtimestamp(now)
        slot = f"{local:%Y-%m-%d} {local.hour:02d}:{local.minute:02d}"
        if not any((local.hour, local.minute) == s for s in SLOTS):
            return []
        if slot in _done_slots():
            return []
        _mark_slot(slot)
        return self.sync_now(f"定时 {local.hour:02d}:{local.minute:02d}")

    def sync_now(self, reason: str) -> list[dict[str, Any]]:
        """真正跑一次同步；总开关在这里拦。"""
        if not store.enabled():
            store.add_log("blocked", f"{reason}：总开关已关闭")
            return []

        try:
            items = chaoxing.fetch_assignments()
        except chaoxing.SessionExpired as e:
            # 登录失效：停这次、不重试，写日志 + 弹窗让重新扫码
            store.add_log("expired", reason, detail=str(e))
            store.set_last_sync({"at": time.time(), "status": "expired", "new": 0, "reason": reason})
            notify.study_session_expired(str(e))
            return []
        except Exception as e:  # noqa: BLE001  其它异常本次放弃，等下次触发
            store.add_log("failed", reason, detail=str(e))
            store.set_last_sync({"at": time.time(), "status": "failed", "new": 0, "reason": reason})
            return []

        added = 0
        seen: set[str] = set()
        for it in items:
            if it["id"] in seen:
                continue
            seen.add(it["id"])
            if it["id"] in _imported():
                continue
            if not it.get("due_at"):
                continue
            note = f"学习通作业提醒 · 来源 {reason}"
            result = _add_todo(it["title"], it["due_at"], note)
            if result:
                _mark_imported(it["id"])
                added += 1

        store.add_log("ok", reason, new=added, detail=f"读到 {len(items)} 条作业")
        store.set_last_sync({"at": time.time(), "status": "ok", "new": added, "reason": reason})
        return items


def _add_todo(title: str, due: float, note: str) -> bool:
    """写进本地待办，复用统一的 add，带上 30 分钟出门提醒。"""
    from ..todos import add as todos_add

    if not license.is_guest():
        try:
            todos_add(
                title=title[:200],
                note=note,
                due_at=due,
                end_at=due + 1800,
                priority="normal",
                tags="学习通",
                repeat="once",
                lead_minutes=30,
            )
            return True
        except Exception as e:  # noqa: BLE001
            log.warning("作业写待办失败：%s", e)
    return False


def _done_slots() -> set[str]:
    from ..db import models as meta

    v = meta.kv_get(KEY_DONE, [])
    return set(v) if isinstance(v, list) else set()


def _mark_slot(slot: str) -> None:
    from ..db import models as meta

    slots = _done_slots()
    slots.add(slot)
    # 只留今天的，跨天自动清掉
    today = datetime.now().strftime("%Y-%m-%d")
    slots = {s for s in slots if s.startswith(today)}
    meta.kv_set(KEY_DONE, sorted(slots))


def _imported() -> set[str]:
    from ..db import models as meta

    v = meta.kv_get("study.imported", [])
    return set(v) if isinstance(v, list) else set()


def _mark_imported(aid: str) -> None:
    from ..db import models as meta

    v = _imported()
    v.add(aid)
    meta.kv_set("study.imported", sorted(v)[:2000])


study_sync = StudySync()
