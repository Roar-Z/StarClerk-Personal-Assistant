"""开机自启：只写当前用户的 Run 键，不动系统服务，也不需要管理员权限。

值里带 --bg，开机后直接进托盘，不弹窗口。
"""
from __future__ import annotations

import logging
import os
import sys
from pathlib import Path

log = logging.getLogger("autostart")

_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"
_NAME = "StarClerk"


def supported() -> bool:
    return os.name == "nt"


def command() -> str:
    """源码跑用 pythonw 起 run.py，装好的版本直接起 exe。"""
    if getattr(sys, "frozen", False):
        return f'"{sys.executable}" --bg'
    py = Path(sys.executable)
    gui = py.with_name("pythonw.exe")
    exe = gui if gui.is_file() else py
    run = Path(__file__).resolve().parents[2] / "run.py"
    return f'"{exe}" "{run}" --bg'


def _read() -> str:
    import winreg

    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, _KEY) as k:
            value, _ = winreg.QueryValueEx(k, _NAME)
            return str(value)
    except OSError:
        return ""


def status() -> dict:
    if not supported():
        return {"supported": False, "enabled": False, "command": ""}
    current = _read()
    return {"supported": True, "enabled": bool(current), "command": current}


def set_enabled(on: bool) -> dict:
    if not supported():
        return status()
    import winreg

    with winreg.CreateKey(winreg.HKEY_CURRENT_USER, _KEY) as k:
        if on:
            winreg.SetValueEx(k, _NAME, 0, winreg.REG_SZ, command())
            log.info("开机自启已开启")
        else:
            try:
                winreg.DeleteValue(k, _NAME)
                log.info("开机自启已关闭")
            except FileNotFoundError:
                pass  # 本来就没写，等同于关好了
    return status()
