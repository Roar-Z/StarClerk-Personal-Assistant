"""桌面启动器：挑端口 → 起 uvicorn(线程) → 托盘/热键/悬浮窗(主线程)。

打包后 EXE 双击就是这里：
    python -m app.launcher        正常启动，带悬浮面板
    python -m app.launcher --bg   开机自启用，只留托盘不弹窗
"""
from __future__ import annotations

import logging
import os
import subprocess
import sys
import threading
import time
from pathlib import Path

import httpx
import uvicorn

from .config import ensure_layout, is_frozen, settings
from .db.sqlite import init_db
from .desktop import hotkey, port, tray, watchdog, window
from .log import setup as setup_log
from .tasks.scheduler import runner  # noqa: F401  确保子模块被 PyInstaller 收集

log = logging.getLogger("launcher")

_state: dict = {"server": None, "thread": None, "watchdog": None}


def _url(path: str = "/") -> str:
    return f"http://{settings.app_host}:{settings.app_port}{path}"


def _serve() -> None:
    from .main import app as fastapi_app  # 传对象而非 import 字符串，打包后不依赖 sys.path

    cfg = uvicorn.Config(
        fastapi_app,
        host=settings.app_host,
        port=settings.app_port,
        log_level="warning",
        access_log=False,
    )
    server = uvicorn.Server(cfg)
    _state["server"] = server
    server.run()


def _start_api() -> None:
    t = threading.Thread(target=_serve, name="api", daemon=True)
    _state["thread"] = t
    t.start()


def _wait_ready(timeout: float = 25) -> bool:
    end = time.time() + timeout
    while time.time() < end:
        try:
            if httpx.get(_url("/api/health"), timeout=1).status_code == 200:
                return True
        except Exception:  # noqa: BLE001  还没起来就是连不上，继续等
            pass
        time.sleep(0.4)
    return False


def _relaunch() -> None:
    """线程重启不回来时的最后办法：重新拉起自己，再结束当前进程。"""
    args = [sys.executable]
    if not is_frozen():
        args.append(str(Path(__file__).resolve().parents[1] / "run.py"))
    args.append("--bg")
    subprocess.Popen(args, close_fds=True)
    os._exit(0)


def _restart_backend() -> None:
    log.warning("后端无响应，尝试重启服务线程")
    server = _state.get("server")
    if server is not None:
        server.should_exit = True
    thread = _state.get("thread")
    if thread is not None:
        thread.join(timeout=10)
    _start_api()
    if _wait_ready(20):
        log.info("后端已重新就绪")
        return
    log.error("重启不成功，改为重启整个进程")
    _relaunch()


def _quit() -> None:
    """托盘退出：直接结束进程，避免 uvicorn/webview 线程残留。"""
    wd = _state.get("watchdog")
    if wd is not None:
        wd.stop()
    os._exit(0)


def main() -> None:
    silent = "--bg" in sys.argv[1:]
    setup_log()
    ensure_layout()
    init_db()

    picked = port.pick(settings.app_host, settings.app_port)
    if picked is None:
        port.alert("StarClerk 启动失败", f"从 {settings.app_port} 往后六个端口都被占了，先关掉占用的程序再试")
        return
    settings.app_port = picked

    _start_api()
    if not _wait_ready():
        port.alert("StarClerk 启动失败", "本地服务没起来，细节在 logs/app.log，先看看有没有依赖缺失")
        return

    if settings.tray_enabled:
        tray.start(on_open=window.open_panel, on_quit=_quit)
    hotkey.start(settings.hotkey, window.open_panel)

    wd = watchdog.Watchdog(_url("/api/health"), _restart_backend)
    _state["watchdog"] = wd
    wd.start()

    if silent:
        log.info("后台模式启动，托盘常驻")
        threading.Event().wait()
    elif settings.window_mode == "webview":
        window.run_window()
    elif settings.window_mode == "browser":
        window.open_panel()
        threading.Event().wait()  # 常驻，靠托盘退出
    else:
        threading.Event().wait()


if __name__ == "__main__":
    main()
