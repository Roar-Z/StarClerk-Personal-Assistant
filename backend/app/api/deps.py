"""接口层公共依赖：统一异常出口（日志 + errors 表 + 可读 detail）。"""
from __future__ import annotations

from fastapi import HTTPException

from .. import fault


def failure(scope: str, exc: Exception, status: int = 502) -> HTTPException:
    """业务异常统一处理：前端只看到一句人话，细节由 fault 记下来。

    接口内部一般不用自己写 except，这里只是为了把压成可读文案再抛。
    """
    msg = fault.report(scope, exc, notify=False)
    return HTTPException(status, f"{scope} 执行失败：{msg}")
