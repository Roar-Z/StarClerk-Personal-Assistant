# PyInstaller：单文件 EXE（无控制台），前端 dist 打进包内
# 构建：pyinstaller build/starclerk.spec --noconfirm
import sys
from pathlib import Path

ROOT = Path(SPECPATH).parent


def hidden():
    return [
        "app.main", "app.launcher", "uvicorn.logging", "uvicorn.loops.auto",
        "uvicorn.protocols.http.auto", "uvicorn.protocols.websockets.auto",
        "uvicorn.lifespan.on", "langgraph", "lancedb", "pyarrow",
    ]


a = Analysis(
    [str(ROOT / "backend" / "run.py")],
    pathex=[str(ROOT / "backend")],
    binaries=[],
    datas=[(str(ROOT / "frontend" / "dist"), "frontend_dist")],
    hiddenimports=hidden(),
    excludes=["tkinter", "matplotlib", "scipy", "pandas", "pytest", "IPython"],
    noarchive=False,
)

pyz = PYZ(a.pure)
exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name="StarClerk",
    debug=False,
    strip=False,
    upx=False,
    console=False,
    icon=None,
)
