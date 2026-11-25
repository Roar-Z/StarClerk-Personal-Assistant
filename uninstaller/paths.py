"""卸载程序自己的路径表。

没复用 app/config.py 是因为那个文件会连带把 pydantic、数据库这些依赖拉进来，
卸载程序就一个删文件的工具，没必要背这么大一坨。
"""
from __future__ import annotations

import os
import sys
from pathlib import Path


def install_dir() -> Path:
    """打包后在 exe 旁边；源码跑就是项目根目录。"""
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent.parent


def is_frozen() -> bool:
    return bool(getattr(sys, "frozen", False))


def _env_value(key: str) -> str:
    """用户可能把数据目录改到别的盘，得先读 .env 再决定删哪儿。"""
    env = install_dir() / ".env"
    if not env.is_file():
        return ""
    try:
        for line in env.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, v = line.split("=", 1)
            if k.strip() == key:
                return v.strip()
    except OSError:
        pass
    return ""


def data_dir() -> Path:
    raw = os.environ.get("DATA_DIR") or _env_value("DATA_DIR") or "./data"
    p = Path(raw)
    return p if p.is_absolute() else install_dir() / p


def db_file() -> Path:
    return data_dir() / "starcLerk.db"


def lancedb_dir() -> Path:
    """知识库分块和记忆向量都在这个目录里。"""
    return data_dir() / "lancedb"


def upload_dir() -> Path:
    return data_dir() / "uploads"


def license_file() -> Path:
    return data_dir() / "license.json"


def log_dir() -> Path:
    return install_dir() / "logs"


def env_file() -> Path:
    return install_dir() / ".env"


def port() -> int:
    raw = os.environ.get("APP_PORT") or _env_value("APP_PORT") or "8756"
    try:
        return int(raw)
    except ValueError:
        return 8756


def ui_dir() -> Path:
    """onefile 打包后资源解到 _MEIPASS，__file__ 也在那里，所以这样写是准的。"""
    return Path(__file__).resolve().parent / "ui"


def size_of(path: Path) -> int:
    """目录大小，权限不够或不存在就当 0，卸载器没必要因为这个报错。"""
    try:
        if path.is_file():
            return path.stat().st_size
        if not path.is_dir():
            return 0
    except OSError:
        return 0

    total = 0
    for root, _dirs, files in os.walk(path):
        for name in files:
            try:
                total += (Path(root) / name).stat().st_size
            except OSError:
                continue
    return total


def human(n: int) -> str:
    """文件大小给人看，保留一位小数就够了。"""
    if n <= 0:
        return "0 B"
    units = ["B", "KB", "MB", "GB", "TB"]
    i = 0
    value = float(n)
    while value >= 1024 and i < len(units) - 1:
        value /= 1024
        i += 1
    return f"{value:.0f} {units[i]}" if i == 0 else f"{value:.1f} {units[i]}"
