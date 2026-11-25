"""托管任务调度子线程：独立线程轮询 tasks 表 → 调 LangGraph → 落库 + 提醒。

为什么用 threading.Thread 而不是 asyncio.Task：
巡检内部是同步的 LangGraph + 可能很慢的本地模型，放在子线程里跑，
即使某次任务卡住也不会拖住 FastAPI 的事件循环（对话/健康检查照常响应）。
单工作线程串行执行，避免本地模型并发把内存/CPU 打满。
"""
from __future__ import annotations

import logging
import threading
import time
from typing import Any

from ..config import settings
from ..db import models as meta
from ..db import sqlite as db
from ..notify.notifier import notify
from .patrol import execute

log = logging.getLogger("scheduler")


class TaskRunner:
    def __init__(self, interval: int | None = None) -> None:
        self.interval = int(interval or settings.scheduler_interval)
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._busy: set[str] = set()  # 本进程正在跑的任务 id
        self._mutex = threading.Lock()

    # ---------------- 生命周期 ----------------
    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._stop.clear()
        self._thread = threading.Thread(target=self._loop, name="task-runner", daemon=True)
        self._thread.start()
        log.info("任务调度子线程已启动（每 %ss 轮询）", self.interval)

    def stop(self, timeout: float = 5) -> None:
        self._stop.set()
        if self._thread:
            self._thread.join(timeout=timeout)
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
        """扫一遍到点任务并串行执行，返回本轮结果（便于排查/测试）。"""
        results = []
        for task in meta.due_tasks(db.now()):
            if self._stop.is_set():
                break
            res = self._run(task)
            if res:
                results.append(res)
        return results

    # ---------------- 单任务 ----------------
    def _run(self, task: dict[str, Any]) -> dict[str, Any] | None:
        tid = task["id"]
        with self._mutex:
            if tid in self._busy:
                return None
            self._busy.add(tid)
        try:
            # 抢占失败说明已被手动执行/其它线程领走，下个周期再说
            if not meta.claim_task(tid, db.now()):
                return None
            return run_task(task)
        finally:
            with self._mutex:
                self._busy.discard(tid)


def run_task(task: dict[str, Any], notify_user: bool = True) -> dict[str, Any]:
    """执行一次巡检：异常收敛成结果，提醒标记交给托盘/SSE。

    notify_user=False 用于「用户手动点执行」——结果已在界面上显示，不再弹托盘。
    """
    name = task.get("name") or "巡检"
    started = time.time()
    try:
        res = execute(task)
    except Exception as e:  # noqa: BLE001
        log.exception("任务 %s 执行失败", name)
        meta.add_error("patrol", f"{name}: {type(e).__name__}: {e}")
        res = {
            "result": f"巡检失败：{str(e)[:200]}",
            "should_notify": True,
            "level": "warn",
            "notice": {"title": f"巡检失败 · {name}", "body": str(e)[:180], "level": "warn"},
        }
    meta.finish_task(task["id"], str(res.get("result") or ""))
    if notify_user:
        if not res.get("ok", True):
            # 巡检本身失败（模型/向量不可用）也要告诉用户，否则“静默成功”更糟
            notify(f"巡检失败 · {name}", str(res.get("result") or "未知错误")[:180], "warn")
        elif res.get("should_notify") and res.get("notice"):
            notice = res["notice"]
            notify(notice["title"], notice["body"], notice.get("level", "info"))
    log.info(
        "任务 %s 本轮结束：%.1fs，提醒=%s", name, time.time() - started, bool(res.get("should_notify"))
    )
    return res


runner = TaskRunner()
