"""全局快捷键（pynput），默认 Ctrl+Alt+Space 唤起悬浮面板。

用 Listener 而非 GlobalHotKeys，避免组合键冲突时整个监听失效。
"""
from __future__ import annotations

import logging
import threading
from typing import Callable

from pynput import keyboard

log = logging.getLogger("hotkey")


def _parse(combo: str) -> set:
    """'<ctrl>+<alt>+<space>' → {Key.ctrl, Key.alt, Key.space}"""
    keys: set = set()
    for part in combo.split("+"):
        name = part.strip().strip("<>").lower()
        if not name:
            continue
        if hasattr(keyboard.Key, name):
            keys.add(getattr(keyboard.Key, name))
        elif len(name) == 1:
            keys.add(keyboard.KeyCode.from_char(name))
    return keys


_ALIAS = {
    keyboard.Key.ctrl_l: keyboard.Key.ctrl,
    keyboard.Key.ctrl_r: keyboard.Key.ctrl,
    keyboard.Key.alt_l: keyboard.Key.alt,
    keyboard.Key.alt_r: keyboard.Key.alt,
    keyboard.Key.alt_gr: keyboard.Key.alt,
    keyboard.Key.shift_l: keyboard.Key.shift,
    keyboard.Key.shift_r: keyboard.Key.shift,
    keyboard.Key.cmd_l: keyboard.Key.cmd,
    keyboard.Key.cmd_r: keyboard.Key.cmd,
}


def _norm(key):
    """左右修饰键统一成通用键，否则 Ctrl+Alt 组合永远匹配不上。"""
    return _ALIAS.get(key, key)


def start(combo: str, callback: Callable[[], None]) -> None:
    target = _parse(combo)
    pressed: set = set()
    fired = False

    def on_press(key):
        nonlocal fired
        pressed.add(_norm(key))
        if not fired and target and target.issubset(pressed):
            fired = True
            try:
                callback()
            except Exception:  # noqa: BLE001
                log.exception("快捷键回调异常")

    def on_release(key):
        nonlocal fired
        pressed.discard(_norm(key))
        fired = False

    threading.Thread(
        target=lambda: keyboard.Listener(on_press=on_press, on_release=on_release).start(),
        name="hotkey",
        daemon=True,
    ).start()
    log.info("快捷键已监听：%s", combo)
