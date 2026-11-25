"""安装程序入口。双击 Setup.exe 就开向导，没有命令行参数。"""
from __future__ import annotations

import os
import sys


def _fix_streams() -> None:
    """无控制台打包后 stdout/stderr 是 None，pywebview 一打印就炸。"""
    if sys.stdout is None:
        sys.stdout = open(os.devnull, "w", encoding="utf-8")  # noqa: SIM115
    if sys.stderr is None:
        sys.stderr = open(os.devnull, "w", encoding="utf-8")  # noqa: SIM115


def run_gui() -> int:
    import webview

    from . import paths
    from .bridge import Api

    api = Api()
    html = paths.ui_dir() / "index.html"
    window = webview.create_window(
        "安装 StarClerk",
        html.as_uri(),
        js_api=api,
        width=900,
        height=660,
        resizable=False,
        background_color="#F7F8FA",
    )
    api._window = window
    webview.start()
    return 0


def main() -> int:
    _fix_streams()
    return run_gui()


if __name__ == "__main__":
    raise SystemExit(main())
