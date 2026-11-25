"""pystray 托盘：打开面板 / 设置 / 退出。独立线程运行，退出时停服务。"""
from __future__ import annotations

import logging
import threading
from typing import Callable

import pystray
from PIL import Image, ImageDraw

from ..notify import notifier

log = logging.getLogger("tray")
_icon: pystray.Icon | None = None


def _make_image() -> Image.Image:
    img = Image.new("RGBA", (64, 64), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    d.ellipse((4, 4, 60, 60), fill=(37, 99, 235, 255))
    d.rounded_rectangle((20, 22, 44, 42), radius=4, fill=(255, 255, 255, 255))
    return img


def start(on_open: Callable[[], None], on_quit: Callable[[], None]) -> pystray.Icon | None:
    global _icon
    if _icon is not None:
        return _icon
    menu = pystray.Menu(
        pystray.MenuItem("打开对话面板", lambda: on_open(), default=True),
        pystray.MenuItem("退出", lambda: (on_quit(), _icon.stop())),
    )
    _icon = pystray.Icon("StarClerk", _make_image(), "StarClerk · 桌面助手", menu)
    threading.Thread(target=_icon.run, name="tray", daemon=True).start()
    notifier.bind_icon(_icon)
    log.info("托盘已就绪")
    return _icon
