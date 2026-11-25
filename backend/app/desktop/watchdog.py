"""健康检测：托盘常驻后隔一会儿问一句后端还在不在。

连续几次问不通就当它挂了，交给外面重启（先拉服务线程，不行再拉进程）。
"""
from __future__ import annotations

import logging
import threading

import httpx

log = logging.getLogger("watchdog")

INTERVAL = 20
MAX_FAILS = 3


class Watchdog(threading.Thread):
    def __init__(self, url: str, on_dead, interval: int = INTERVAL) -> None:
        super().__init__(name="watchdog", daemon=True)
        self.url = url
        self.on_dead = on_dead
        self.interval = interval
        self._stop = threading.Event()

    def stop(self) -> None:
        self._stop.set()

    def _alive(self) -> bool:
        try:
            return httpx.get(self.url, timeout=4).status_code == 200
        except Exception:  # noqa: BLE001  超时、拒绝连接都算不通
            return False

    def run(self) -> None:
        # 刚起来服务还在初始化，先安静等一轮再开始探
        if self._stop.wait(self.interval):
            return
        fails = 0
        while not self._stop.wait(self.interval):
            if self._alive():
                if fails:
                    log.info("后端恢复正常")
                fails = 0
                continue
            fails += 1
            log.warning("健康检测失败 %d/%d", fails, MAX_FAILS)
            if fails < MAX_FAILS:
                continue
            fails = 0
            try:
                self.on_dead()
            except Exception:  # noqa: BLE001  自愈本身出错，线程也不能停
                log.exception("重启后端时出错")
