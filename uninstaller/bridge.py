"""页面能调的后端方法，就这几个，别再多开了。

pywebview 会把这里的方法挂到 window.pywebview.api 上，
返回值必须能 JSON 序列化，所以全部用 dict，不扔异常出去。
"""
from __future__ import annotations

import os

from . import guard, paths, purge


class Api:
    def __init__(self) -> None:
        # 一定得带下划线，pywebview 会反射所有公开属性，
        # 暴露一个窗口对象出去会一直往下递归，界面根本起不来。
        self._window = None

    def scan(self) -> dict:
        try:
            return purge.scan()
        except Exception as e:  # noqa: BLE001  扫描失败也要把原因给页面
            return {"error": f"读取磁盘信息失败：{e}", "items": []}

    def run(self, keys: list[str]) -> dict:
        try:
            return purge.run(list(keys or []))
        except Exception as e:  # noqa: BLE001
            return {"ok": False, "message": str(e), "results": []}

    def stop_app(self) -> dict:
        return guard.stop()

    def reveal(self, target: str = "data") -> dict:
        path = {
            "data": paths.data_dir(),
            "logs": paths.log_dir(),
            "install": paths.install_dir(),
        }.get(target, paths.data_dir())
        try:
            os.startfile(str(path))  # noqa: S606
            return {"ok": True}
        except OSError as e:
            return {"ok": False, "message": str(e)}

    def close(self) -> bool:
        if self._window is not None:
            self._window.destroy()
        return True
