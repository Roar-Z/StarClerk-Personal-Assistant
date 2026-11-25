"""桌面启动器：uvicorn(线程) + 托盘(线程) + 快捷键(线程) + 悬浮窗(主线程)。

打包后 EXE 双击即此入口：
    python -m app.launcher
"""
from __future__ import annotations

import logging
import os
import threading
import time

import httpx
import uvicorn

from .config import settings
from .db.sqlite import init_db
from .desktop import hotkey, tray, window
from .tasks.scheduler import runner  # noqa: F401  确保子模块被 PyInstaller 收集

log = logging.getLogger("launcher")


def _serve() -> None:
    from .main import app as fastapi_app  # 传对象而非 import 字符串，打包后不依赖 sys.path

    uvicorn.run(
        fastapi_app,
        host=settings.app_host,
        port=settings.app_port,
        log_level="warning",
        access_log=False,
    )


def _quit() -> None:
    """托盘退出：直接结束进程，避免 uvicorn/webview 线程残留。"""
    try:
        os._exit(0)
    except Exception:  # noqa: BLE001
        pass


def _wait_ready(timeout: float = 20) -> bool:
    url = f"http://{settings.app_host}:{settings.app_port}/api/health"
    end = time.time() + timeout
    while time.time() < end:
        try:
            if httpx.get(url, timeout=1).status_code == 200:
                return True
        except Exception:  # noqa: BLE001
            time.sleep(0.4)
    return False


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    init_db()
    threading.Thread(target=_serve, name="api", daemon=True).start()
    if not _wait_ready():
        log.error("后端启动失败，请检查端口 %s 是否被占用", settings.app_port)
        return

    if settings.tray_enabled:
        tray.start(on_open=window.open_panel, on_quit=_quit)
    hotkey.start(settings.hotkey, window.open_panel)

    if settings.window_mode == "webview":
        window.run_window()
    elif settings.window_mode == "browser":
        window.open_panel()
        threading.Event().wait()  # 常驻，靠托盘退出
    else:
        threading.Event().wait()


if __name__ == "__main__":
    main()
