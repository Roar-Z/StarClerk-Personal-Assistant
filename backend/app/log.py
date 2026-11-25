"""日志：控制台 + 按大小滚动的文件，出问题先翻 logs/app.log。

单个文件写到 2MB 就切一份，只留最近几份，超过一周的顺手删掉，
本地跑一年也不至于把磁盘塞满。页面上的「导出日志」就是把 logs 打成一个 zip。
"""
from __future__ import annotations

import io
import logging
import sys
import time
import zipfile
from logging.handlers import RotatingFileHandler

from .config import settings

_FMT = "%(asctime)s %(levelname)-7s %(name)-14s %(message)s"
_DATE = "%m-%d %H:%M:%S"

MAX_BYTES = 2 * 1024 * 1024
KEEP_BACKUPS = 4
EXPIRE_DAYS = 7


def _formatter() -> logging.Formatter:
    return logging.Formatter(_FMT, _DATE)


def setup(level: int = logging.INFO) -> None:
    root = logging.getLogger()
    # 打包后 launcher 和 uvicorn 都会进来配一次，标记一下别加重复的 handler
    if getattr(root, "_sc_ready", False):
        return
    root.setLevel(level)

    if sys.stderr is not None:  # console=False 打包后 stderr 可能是 None
        console = logging.StreamHandler()
        console.setFormatter(_formatter())
        root.addHandler(console)

    rolling = RotatingFileHandler(
        settings.log_path / "app.log",
        maxBytes=MAX_BYTES,
        backupCount=KEEP_BACKUPS,
        encoding="utf-8",
    )
    rolling.setFormatter(_formatter())
    root.addHandler(rolling)

    for noisy in ("httpx", "httpcore", "watchfiles", "uvicorn.access"):
        logging.getLogger(noisy).setLevel(logging.WARNING)

    root._sc_ready = True  # type: ignore[attr-defined]
    logging.getLogger("log").info("日志目录：%s", settings.log_path)
    prune()


def prune(days: int = EXPIRE_DAYS) -> int:
    """清太旧的日志；正在写的 app.log 修改时间一直在变，不会被误删。"""
    line = time.time() - max(1, days) * 86400
    removed = 0
    for p in settings.log_path.glob("app.log*"):
        try:
            if p.stat().st_mtime < line:
                p.unlink()
                removed += 1
        except OSError:
            continue
    if removed:
        logging.getLogger("log").info("清理过期日志 %d 个", removed)
    return removed


def files() -> list[dict]:
    """日志列表给系统页展示，新的排前面。"""
    out: list[dict] = []
    for p in settings.log_path.glob("app.log*"):
        try:
            st = p.stat()
        except OSError:
            continue
        out.append({"name": p.name, "size": st.st_size, "mtime": st.st_mtime})
    return sorted(out, key=lambda x: x["mtime"], reverse=True)


def export_bytes() -> bytes:
    """直接在内存里打包，不落临时文件，导完就丢。"""
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        for p in sorted(settings.log_path.glob("app.log*")):
            if p.is_file():
                z.write(p, arcname=p.name)
    return buf.getvalue()
