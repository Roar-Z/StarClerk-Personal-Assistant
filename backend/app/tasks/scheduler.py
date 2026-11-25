"""托管任务调度子线程：独立线程轮询 tasks 表 → 丢进队列 → 由小队慢慢跑。

为什么用 threading.Thread 而不是 asyncio.Task：
巡检内部是同步的 LangGraph + 可能很慢的本地模型，放在子线程里跑，
即使某次任务卡住也不会拖住 FastAPI 的事件循环（对话/健康检查照常响应）。

错峰的做法有两层：
- 扫描到一批到点任务时，按顺序给它们排队，第 n 个延后 n*stagger 秒；
- 每次跑完写回下次时间时加一点随机抖动，几台机器/几条任务不会永远撞在一起。
低配模式（性能模式）下把轮询间隔和任务间隔都拉长，工作线程也只留 1 个。
"""
from __future__ import annotations

import logging
import random
import threading
import time
from typing import Any

from .. import license
from ..config import settings
from ..db import models as meta
from ..db import sqlite as db
from .queue import patrol_queue
from .worker import run_task

log = logging.getLogger("scheduler")

__all__ = ["TaskRunner", "runner", "run_task"]


def _scale() -> float:
    """性能模式：所有间隔按倍数拉长，机器不忙的时候还能再开会话。"""
    return 2.0 if license.perf_mode() else 1.0


def effective_interval() -> int:
    base = int(settings.scheduler_interval or 20)
    return int(base * _scale())


def stagger_gap() -> int:
    """同一批到点任务的间隔，避免一起打模型。"""
    return 20 if license.perf_mode() else 8


class TaskRunner:
    def __init__(self, interval: int | None = None) -> None:
        self._interval = interval
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    @property
    def interval(self) -> int:
        return int(self._interval or effective_interval())

    # ---------------- 生命周期 ----------------
    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._stop.clear()
        patrol_queue.start(1 if license.perf_mode() else license.MAX_CONCURRENCY)
        self._thread = threading.Thread(target=self._loop, name="task-runner", daemon=True)
        self._thread.start()
        log.info("任务调度子线程已启动（每 %ss 轮询，错峰 %ss）", self.interval, stagger_gap())

    def stop(self, timeout: float = 5) -> None:
        self._stop.set()
        if self._thread:
            self._thread.join(timeout=timeout)
        patrol_queue.stop(timeout)
        self._thread = None
        log.info("任务调度子线程已停止")

    @property
    def alive(self) -> bool:
        return bool(self._thread and self._thread.is_alive())

    # ---------------- 主循环 ----------------
    def _loop(self) -> None:
        while not self._stop.is_set():
            try:
                self.tick()
            except Exception as e:  # noqa: BLE001  调度本身不能死
                log.exception("调度轮询异常")
                meta.add_error("scheduler", f"{type(e).__name__}: {e}")
            if self._stop.wait(self.interval):
                break

    def tick(self) -> list[dict[str, Any]]:
        """扫一遍到点任务，按到期顺序排队；返回本轮排进去的任务。"""
        now = db.now()
        due = sorted(meta.due_tasks(now), key=lambda t: t.get("next_run_at") or 0)
        queued: list[dict[str, Any]] = []
        gap = stagger_gap()
        for i, task in enumerate(due):
            if self._stop.is_set():
                break
            # 先抢执行权（会把 next_run 推后），抢不到说明别处已经在跑
            if not meta.claim_task(task["id"], now, _scale()):
                continue
            if patrol_queue.put(task, delay=i * gap):
                queued.append(task)
            else:
                # 队列里已经有一条了，把时间退回去一点，别白等一个周期
                meta.restore_next_run(task["id"], now + gap)
        return queued

    # ---------------- 状态 ----------------
    def status(self) -> dict[str, Any]:
        return {
            "alive": self.alive,
            "interval": self.interval,
            "stagger": stagger_gap(),
            "perf_mode": license.perf_mode(),
            "queue": patrol_queue.status(),
        }


runner = TaskRunner()
