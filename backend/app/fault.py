"""异常翻译：底层报错五花八门，界面上只该看到一句人话。

report() 固定做三件事——写日志、进 errors 表、推一条提醒（托盘气泡 + 前端弹窗）。
大模型超时、Key 写错、连不上、向量库读坏、文件没权限，都从这里出去。
"""
from __future__ import annotations

import logging

from .db import models as meta
from .notify import notifier

log = logging.getLogger("fault")

# 关键字 → 提示语；顺序有讲究，先匹配到的先用
_RULES: tuple[tuple[tuple[str, ...], str], ...] = (
    (("timeout", "timed out", "readtimeout"), "模型响应超时了，检查网络，或者把模型换成更快的再试"),
    (("401", "invalid api key", "unauthorized", "authentication"), "API Key 不对，去「模型」页重新填一次"),
    (("403", "forbidden"), "这个账号没权限调用该模型，换一个或者换 Key"),
    (("429", "rate limit", "quota"), "调用太频繁被限流了，等一分钟再试"),
    (("connection", "getaddrinfo", "unreachable", "network"), "连不上模型服务，确认地址填对、Ollama 有没有启动"),
    (("lance", "pyarrow", "arrow", "dataset"), "向量库读写失败，可以到「系统」页清空后重新导入资料"),
    (("no space", "read-only", "disk", "permission denied"), "文件读写失败，看看磁盘空间和目录权限"),
)

_FALLBACK = "中途出了点问题，细节已经写进日志了"


def describe(exc: BaseException) -> str:
    text = f"{type(exc).__name__} {exc}".lower()
    for keys, msg in _RULES:
        if any(k in text for k in keys):
            return msg
    return _FALLBACK


def report(scope: str, exc: BaseException, notify: bool = True, title: str = "运行异常") -> str:
    """返回一句可以直接给用户看的话；要不要继续往外抛由调用方决定。"""
    msg = describe(exc)
    log.error("[%s] %s: %s", scope, type(exc).__name__, exc)
    try:
        meta.add_error(scope, f"{type(exc).__name__}: {exc}")
    except Exception:  # noqa: BLE001  入库失败不能反过来打断主流程
        log.debug("异常入库失败", exc_info=True)
    if notify:
        notifier.notify(title, msg, "warn")
    return msg
