# -*- mode: python ; coding: utf-8 -*-
# 安装程序：单文件 Setup.exe，自带一份 app/ 的程序文件
# 打包前先把主程序打出来（dist/StarClerk），不然装出来是空的
from pathlib import Path

from PyInstaller.utils.hooks import collect_submodules

ROOT = Path(SPECPATH).parent
APP_DIR = ROOT / "dist" / "StarClerk"
UNINSTALLER = ROOT / "dist" / "Uninstall.exe"

hidden = collect_submodules("webview") + [
    "webview.platforms.winforms",
    "webview.platforms.edgechromium",
    "clr",
]

datas = [
    (str(ROOT / "installer" / "ui"), "installer/ui"),
    (str(ROOT / "uninstaller" / "ui"), "uninstaller/ui"),  # 安装页复用这份样式
]

if APP_DIR.is_dir():
    datas.append((str(APP_DIR), "app"))
if UNINSTALLER.is_file():
    datas.append((str(UNINSTALLER), "app"))

a = Analysis(
    [str(ROOT / "build" / "install_entry.py")],
    pathex=[str(ROOT)],
    binaries=[],
    datas=datas,
    hiddenimports=hidden,
    hookspath=[],
    runtime_hooks=[],
    excludes=["fastapi", "uvicorn", "pydantic", "lancedb", "pyarrow", "PIL", "numpy", "pandas"],
    noarchive=False,
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name="Setup",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,
)
