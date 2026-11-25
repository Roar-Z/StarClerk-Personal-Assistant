"""接口层公共依赖：统一异常出口（日志 + errors 表 + 可读 detail）。"""
from __future__ import annotations

import logging

from fastapi import HTTPException

from ..db import models as meta

log = logging.getLogger("api")


def failure(scope: str, exc: Exception, status: int = 502) -> HTTPException:
    """业务异常统一处理：前端只看到一句人话，细节进日志和 errors 表。"""
    log.exception("[%s] %s", scope, exc)
    try:
        meta.add_error(scope, f"{type(exc).__name__}: {exc}")
    except Exception:  # noqa: BLE001  记日志失败不能影响返回
        log.debug("异常入库失败", exc_info=True)
    return HTTPException(status, f"{scope} 执行失败：{str(exc)[:200]}")
