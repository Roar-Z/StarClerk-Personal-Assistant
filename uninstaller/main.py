"""卸载程序入口。

平时双击 Uninstall.exe 就是开窗口；
加 --list / --purge 可以不开界面，直接看清单或者按参数删（自己排查问题方便）。
"""
from __future__ import annotations

import argparse
import json
import os
import sys

from . import paths, purge


def _fix_streams() -> None:
    """打包成无控制台程序后 stdout/stderr 是 None，pywebview 一打印就报错，
    顺手把它们指到空设备上，省得窗口因此起不来。"""
    if sys.stdout is None:
        sys.stdout = open(os.devnull, "w", encoding="utf-8")  # noqa: SIM115
    if sys.stderr is None:
        sys.stderr = open(os.devnull, "w", encoding="utf-8")  # noqa: SIM115


def _print(data: dict) -> None:
    print(json.dumps(data, ensure_ascii=False, indent=2))


def run_cli(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(prog="Uninstall", description="StarClerk 卸载程序")
    ap.add_argument("--list", action="store_true", help="只列出可删除项，不动文件")
    ap.add_argument("--purge", default="", help="按逗号分隔的 key 删除，例如 logs,usage")
    ap.add_argument("--stop", action="store_true", help="结束正在运行的主程序")
    args = ap.parse_args(argv)

    if args.stop:
        from . import guard

        _print(guard.stop())
        return 0
    if args.list:
        _print(purge.scan())
        return 0
    if args.purge:
        keys = [k.strip() for k in args.purge.split(",") if k.strip()]
        result = purge.run(keys)
        _print(result)
        return 0 if result.get("ok") else 1
    return -1


def run_gui() -> int:
    import webview

    from .bridge import Api

    api = Api()
    html = paths.ui_dir() / "index.html"
    window = webview.create_window(
        "卸载 StarClerk",
        html.as_uri(),
        js_api=api,
        width=880,
        height=700,
        min_size=(760, 620),
        background_color="#F7F8FA",
    )
    api._window = window
    webview.start()
    return 0


def main(argv: list[str] | None = None) -> int:
    _fix_streams()
    args = list(sys.argv[1:] if argv is None else argv)
    if args:
        code = run_cli(args)
        if code >= 0:
            return code
    return run_gui()


if __name__ == "__main__":
    raise SystemExit(main())
