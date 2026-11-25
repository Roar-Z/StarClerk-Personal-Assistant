# -*- mode: python ; coding: utf-8 -*-
# 卸载程序：单文件 exe，名称 Uninstall.exe，跟 StarClerk.exe 放同一个目录
from pathlib import Path

from PyInstaller.utils.hooks import collect_submodules

ROOT = Path(SPECPATH).parent

hidden = collect_submodules("webview") + [
    "webview.platforms.winforms",
    "webview.platforms.edgechromium",
    "clr",
]

a = Analysis(
    [str(ROOT / "build" / "uninstall_entry.py")],
    pathex=[str(ROOT)],
    binaries=[],
    datas=[(str(ROOT / "uninstaller" / "ui"), "uninstaller/ui")],
    hiddenimports=hidden,
    hookspath=[],
    runtime_hooks=[],
    excludes=[
        "fastapi",
        "uvicorn",
        "pydantic",
        "lancedb",
        "pyarrow",
        "PIL",
        "numpy",
        "pandas",
        "matplotlib",
    ],
    noarchive=False,
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name="Uninstall",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,
    disable_windowed_traceback=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
