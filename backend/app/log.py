"""日志格式只在这里定义，launcher 和 API 进程各调一次，排错时输出能对上。"""
from __future__ import annotations

import logging

_FORMAT = "%(asctime)s %(levelname)-7s %(name)-14s %(message)s"


def setup(level: int = logging.INFO) -> None:
    root = logging.getLogger()
    if root.handlers:  # 已有 handler（比如 uvicorn 先配过）就不重复加
        return
    logging.basicConfig(level=level, format=_FORMAT, datefmt="%H:%M:%S")
    for noisy in ("httpx", "httpcore", "watchfiles"):
        logging.getLogger(noisy).setLevel(logging.WARNING)
