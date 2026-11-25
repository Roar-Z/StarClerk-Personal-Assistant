"""端口占用处理：配置的端口被占就往后顺延几个，都不行再弹窗。

Windows 上不用 SO_REUSEADDR，否则端口被人家听着也能 bind 成功，
那样请求会跑到别的进程里去，反而更难查。
"""
from __future__ import annotations

import ctypes
import logging
import socket

log = logging.getLogger("port")


def free(host: str, port: int) -> bool:
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        s.bind((host, port))
        return True
    except OSError:
        return False
    finally:
        s.close()


def pick(host: str, base: int, tries: int = 6) -> int | None:
    """从配置端口开始往后找，返回第一个能用的；都占了返回 None。"""
    for p in range(base, base + tries):
        if free(host, p):
            if p != base:
                log.warning("端口 %s 被占用，顺延到 %s", base, p)
            return p
    return None


def alert(title: str, text: str) -> None:
    """启动阶段托盘还没起来，失败只能靠系统弹窗告诉用户。"""
    log.error("%s：%s", title, text)
    try:
        ctypes.windll.user32.MessageBoxW(None, text, title, 0x10)
    except Exception:  # noqa: BLE001  非 Windows 就只留日志
        pass
