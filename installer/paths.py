"""安装程序的路径，跟卸载器那份分开写，免得互相牵连。"""
from __future__ import annotations

import os
import sys
from pathlib import Path

APP_EXE = "StarClerk.exe"
UNINST_EXE = "Uninstall.exe"
APP_NAME = "StarClerk"
APP_VERSION = "0.2.0"


def is_frozen() -> bool:
    return bool(getattr(sys, "frozen", False))


def install_dir() -> Path:
    """安装包自己所在的目录（源码跑就是项目根）。"""
    if is_frozen():
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent.parent


def ui_dir() -> Path:
    return Path(__file__).resolve().parent / "ui"


def _meipass() -> Path:
    return Path(getattr(sys, "_MEIPASS", install_dir()))


def payload_dir() -> Path:
    """要装出去的那堆文件：打包时塞进 app/，源码跑就找项目里的 dist/StarClerk。"""
    env = os.environ.get("SETUP_PAYLOAD")
    if env:
        return Path(env)
    packed = _meipass() / "app"
    if packed.is_dir():
        return packed
    return install_dir() / "dist" / "StarClerk"


def has_payload() -> bool:
    return (payload_dir() / APP_EXE).is_file() or any(payload_dir().glob("*"))


def default_target() -> Path:
    """默认装到当前用户目录，不弹 UAC，国内软件基本都这么干。"""
    base = os.environ.get("LOCALAPPDATA") or str(Path.home() / "AppData" / "Local")
    return Path(base) / "Programs" / APP_NAME


def size_of(path: Path) -> int:
    if path.is_file():
        return path.stat().st_size
    total = 0
    for root, _dirs, files in os.walk(path):
        for name in files:
            try:
                total += (Path(root) / name).stat().st_size
            except OSError:
                continue
    return total


def human(n: int) -> str:
    if n <= 0:
        return "0 B"
    units = ["B", "KB", "MB", "GB", "TB"]
    i = 0
    value = float(n)
    while value >= 1024 and i < len(units) - 1:
        value /= 1024
        i += 1
    return f"{value:.0f} {units[i]}" if i == 0 else f"{value:.1f} {units[i]}"


def free_space(path: Path) -> int:
    """目标盘剩多少，看最近的已存在目录。"""
    p = path
    while not p.exists() and p.parent != p:
        p = p.parent
    try:
        return __import__("shutil").disk_usage(str(p)).free
    except OSError:
        return 0
