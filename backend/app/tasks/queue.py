"""巡检队列：到点先排队，再由固定几个小工线程挨个跑。

为什么不直接在扫描循环里跑：
1. 同一时刻到点的任务可能有好几条，一起打模型会卡；
2. 排队后可以按 due 时间错峰，隔几秒执行一条；
3. 性能模式下调小工数量就完事，调度那边不用改。

真正限制模型并发的是 llm/client 里的信号量（最多 2 路），这里是第二道闸。
"""
from __future__ import annotations

import heapq
import itertools
import logging
import threading
import time
from typing import Any

from ..license import MAX_CONCURRENCY
from .worker import run_task

log = logging.getLogger("queue")


class PatrolQueue:
    def __init__(self, workers: int = MAX_CONCURRENCY) -> None:
        self.workers = max(1, min(int(workers), MAX_CONCURRENCY))
        self._heap: list[tuple[float, int, dict[str, Any]]] = []
        self._seq = itertools.count()
        self._cv = threading.Condition()
        self._pending: set[str] = set()
        self._stop = threading.Event()
        self._threads: list[threading.Thread] = []
        self._done = 0

    # ---------------- 生命周期 ----------------
    def start(self, workers: int | None = None) -> None:
        if workers:
            self.workers = max(1, min(int(workers), MAX_CONCURRENCY))
        if any(t.is_alive() for t in self._threads):
            return
        self._stop.clear()
        self._threads = [
            threading.Thread(target=self._loop, name=f"patrol-{i}", daemon=True)
            for i in range(self.workers)
        ]
        for t in self._threads:
            t.start()
        log.info("巡检队列启动，%d 个工作线程", self.workers)

    def stop(self, timeout: float = 5) -> None:
        self._stop.set()
        with self._cv:
            self._cv.notify_all()
        for t in self._threads:
            t.join(timeout=timeout)
        self._threads = []
        with self._cv:
            self._heap.clear()
            self._pending.clear()

    # ---------------- 入队 ----------------
    def put(self, task: dict[str, Any], delay: float = 0.0) -> bool:
        """同一个任务还在队列里就不重复放，返回是否真的入队了。"""
        tid = str(task.get("id"))
        with self._cv:
            if tid in self._pending:
                return False
            self._pending.add(tid)
            heapq.heappush(self._heap, (time.time() + max(0.0, delay), next(self._seq), task))
            self._cv.notify()
        return True

    # ---------------- 工作线程 ----------------
    def _loop(self) -> None:
        while not self._stop.is_set():
            task = self._take()
            if task is None:
                continue
            try:
                run_task(task)
                with self._cv:
                    self._done += 1
            except Exception as e:  # noqa: BLE001  线程不能因为一条任务挂掉
                log.exception("队列执行任务失败")
                from ..db import models as meta

                meta.add_error("queue", f"{task.get('name')}: {type(e).__name__}: {e}")
            finally:
                with self._cv:
                    self._pending.discard(str(task.get("id")))

    def _take(self) -> dict[str, Any] | None:
        with self._cv:
            while not self._heap and not self._stop.is_set():
                self._cv.wait(0.5)
            if self._stop.is_set():
                return None
            due, _, task = self._heap[0]
            wait = due - time.time()
            if wait > 0:
                # 还没到点，先眯一会儿（最多一秒，方便随时响应停止）
                self._cv.wait(min(wait, 1.0))
                return None
            heapq.heappop(self._heap)
            return task

    # ---------------- 状态 ----------------
    def status(self) -> dict[str, int]:
        with self._cv:
            return {"workers": self.workers, "queued": len(self._heap), "done": self._done}


patrol_queue = PatrolQueue()
