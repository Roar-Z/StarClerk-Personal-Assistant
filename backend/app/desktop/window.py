"""悬浮窗：pywebview（Win10/11 自带 WebView2，不额外装浏览器）。

关闭窗口 = 隐藏到托盘，不退出进程；快捷键/托盘再唤起。
无 pywebview 时退化为默认浏览器打开。
"""
from __future__ import annotations

import logging
import webbrowser

log = logging.getLogger("window")

_window = None


def _url() -> str:
    from ..config import settings

    return f"http://{settings.app_host}:{settings.app_port}/"


def open_panel() -> None:
    if _window is not None:
        try:
            _window.show()
            _window.restore()
            _window.evaluate_js("window.__starclerkFocus && window.__starclerkFocus()")
            return
        except Exception:  # noqa: BLE001  窗口已销毁则重建
            pass
    webbrowser.open(_url())


def run_window() -> None:
    """主线程阻塞运行（pywebview 要求）。托盘/快捷键线程可调 open_panel()。"""
    global _window
    try:
        import webview
    except Exception:  # noqa: BLE001
        log.warning("pywebview 不可用，改为浏览器模式")
        open_panel()
        return

    _window = webview.create_window(
        "StarClerk",
        _url(),
        width=1120,
        height=760,
        min_size=(920, 620),
        x=80,
        y=60,
        resizable=True,
        easy_drag=False,
        on_top=False,         # 桌面应用形态：不置顶，快捷键唤起时置前
        frameless=False,
        background_color="#F7F8FA",
    )
    _window.events.closing += _on_closing
    webview.start(debug=False)


def _on_closing() -> bool:
    """拦截关闭：隐藏到托盘，返回 False 阻止真正关闭。"""
    try:
        _window.hide()
    except Exception:  # noqa: BLE001
        return True
    return False
