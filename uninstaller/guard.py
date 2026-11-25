"""判断主程序有没有在跑，以及怎么把它关掉。

为什么先关：SQLite 和 LanceDB 都是有连接就能读写的，主程序开着的时候去删数据，
轻则删一半被占用，重则把库写坏。卸载器这边先讲清楚，别糊里糊涂就动手。
"""
from __future__ import annotations

import socket
import subprocess
import time

from . import paths

CREATE_NO_WINDOW = 0x08000000
APP_EXE = "StarClerk.exe"


def port_busy(port: int | None = None, timeout: float = 0.35) -> bool:
    """.env 里的端口能连上，基本就是在跑（也有极小概率是别的程序占着）。"""
    p = port or paths.port()
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.settimeout(timeout)
        return s.connect_ex(("127.0.0.1", p)) == 0


def app_pids() -> list[int]:
    """tasklist 比 psutil 省一个依赖，反正只在 Windows 上用。"""
    try:
        out = subprocess.run(
            ["tasklist", "/FI", f"IMAGENAME eq {APP_EXE}", "/FO", "CSV", "/NH"],
            capture_output=True,
            text=True,
            timeout=8,
            creationflags=CREATE_NO_WINDOW,
        )
    except (OSError, subprocess.SubprocessError):
        return []
    pids: list[int] = []
    for line in out.stdout.splitlines():
        parts = [x.strip().strip('"') for x in line.split('","')]
        if len(parts) >= 2 and parts[0].strip('"').lower() == APP_EXE.lower():
            try:
                pids.append(int(parts[1]))
            except ValueError:
                continue
    return pids


def status() -> dict:
    pids = app_pids()
    busy = port_busy()
    return {
        "running": bool(pids) or busy,
        "pids": pids,
        "port": paths.port(),
        "port_busy": busy,
        # 源码跑的时候进程叫 python.exe，强杀容易误伤，只能让用户自己关
        "can_kill": bool(pids),
    }


def stop() -> dict:
    """先按进程名关，再等等端口，还占着就如实说。"""
    pids = app_pids()
    if not pids:
        return {"ok": False, "message": "没找到 StarClerk.exe，源码模式请手动关掉后端"}
    try:
        subprocess.run(
            ["taskkill", "/IM", APP_EXE, "/F"],
            capture_output=True,
            text=True,
            timeout=10,
            creationflags=CREATE_NO_WINDOW,
        )
    except (OSError, subprocess.SubprocessError) as e:
        return {"ok": False, "message": f"结束进程失败：{e}"}

    for _ in range(10):
        if not port_busy() and not app_pids():
            return {"ok": True, "message": "主程序已关闭"}
        time.sleep(0.3)
    return {"ok": False, "message": "进程还在，可能被系统保护了，手动退出一下"}
