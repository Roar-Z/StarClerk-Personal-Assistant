"""主窗口：pywebview 无边框桌面窗口，拖动/最小化/关闭都由页面右上角按钮触发。

默认居中显示，左侧导航右侧内容；关闭只隐藏，进程留给托盘。
WebView2 缺失时退化为默认浏览器打开。
"""
from __future__ import annotations

import ctypes
import logging
import webbrowser

log = logging.getLogger("window")

_window = None
_origin = (0, 0)  # 拖动开始时的窗口左上角坐标


def _url() -> str:
    from ..config import settings

    return f"http://{settings.app_host}:{settings.app_port}/"


class Bridge:
    """挂给 js_api 的最小方法集，前端用 window.pywebview.api.xxx 调。"""

    def drag_begin(self) -> bool:
        global _origin
        if _window is None:
            return False
        _origin = (_window.x, _window.y)
        return True

    def drag_to(self, mouse_x: int, mouse_y: int, base_x: int, base_y: int) -> bool:
        """前端传屏幕坐标：按下时的基准点 + 当前点，偏移由窗口原点加上，避免累积误差。"""
        if _window is None:
            return False
        _window.move(int(_origin[0] + mouse_x - base_x), int(_origin[1] + mouse_y - base_y))
        return True

    def minimize(self) -> bool:
        if _window is None:
            return False
        _window.minimize()
        return True

    def hide(self) -> bool:
        """关闭按钮：收到托盘里，不退出进程。"""
        if _window is None:
            return False
        _window.hide()
        return True


def _center(width: int, height: int) -> tuple[int, int]:
    """居中摆放，稍微偏上一点，标题栏别顶到屏幕边。"""
    try:
        user32 = ctypes.windll.user32
        sw, sh = user32.GetSystemMetrics(0), user32.GetSystemMetrics(1)
        x = max(0, (sw - width) // 2)
        y = max(0, (sh - height) // 2 - 30)
        return x, y
    except Exception:  # noqa: BLE001  非 Windows 或取屏失败就退回固定位置
        return 80, 60


def open_panel() -> None:
    if _window is not None:
        try:
            _window.show()
            _window.restore()
            _window.evaluate_js("window.__starclerkFocus && window.__starclerkFocus()")
            return
        except Exception:  # noqa: BLE001  窗口销毁了就重新开
            pass
    webbrowser.open(_url())


def run_window() -> None:
    """pywebview 要求跑在主线程，launcher 里直接调。"""
    global _window
    try:
        import webview
    except Exception:  # noqa: BLE001
        log.warning("pywebview 不可用，改为浏览器模式")
        webbrowser.open(_url())
        return

    from ..config import settings

    w, h = settings.window_width, settings.window_height
    x, y = _center(w, h)
    _window = webview.create_window(
        "StarClerk",
        _url(),
        width=w,
        height=h,
        min_size=(980, 640),
        x=x,
        y=y,
        frameless=True,       # 自绘标题栏，跟页面风格统一
        easy_drag=False,
        on_top=False,
        background_color="#F7F8FA",
        js_api=Bridge(),
    )
    _window.events.closing += _on_closing
    webview.start(debug=False)


def _on_closing() -> bool:
    """点系统关闭（Alt+F4 等）也走隐藏，返回 False 阻止真关闭。"""
    try:
        _window.hide()
    except Exception:  # noqa: BLE001
        return True
    return False
