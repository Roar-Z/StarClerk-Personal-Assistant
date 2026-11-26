# PyInstaller：单文件夹版（onedir）
# 好处是调试方便，dist/StarClerk 下的文件可以单独替换、也能直接看 _internal 里少了什么
# 构建：pyinstaller build/starclerk.spec --noconfirm
import sys
from pathlib import Path

from PyInstaller.utils.hooks import collect_data_files, collect_dynamic_libs, collect_submodules

ROOT = Path(SPECPATH).parent

hidden = [
    "app.main",
    "app.launcher",
    "uvicorn.logging",
    "uvicorn.loops.auto",
    "uvicorn.protocols.http.auto",
    "uvicorn.protocols.http.h11_impl",
    "uvicorn.protocols.websockets.auto",
    "uvicorn.lifespan.on",
    "langgraph",
    "lancedb",
    "lance",
    "pyarrow",
    "pystray._win32",
    "webview.platforms.edgechromium",
]

datas = [(str(ROOT / "frontend" / "dist"), "frontend_dist")]
binaries = []

# LanceDB 的 rust 扩展在 lance 包里，不显式收进来打包后一连接就报找不到 dll
for pkg in ("lancedb", "lance"):
    try:
        datas += collect_data_files(pkg)
        binaries += collect_dynamic_libs(pkg)
        hidden += collect_submodules(pkg)
    except Exception:
        pass

# PDF 解析用的 PyMuPDF，扩展库要显式收进来，不然打包后读不了 PDF
for pkg in ("fitz", "pymupdf"):
    try:
        datas += collect_data_files(pkg)
        binaries += collect_dynamic_libs(pkg)
        hidden += collect_submodules(pkg)
    except Exception:
        pass

# 本地 OCR 的模型文件在 rapidocr_onnxruntime 包里，漏收了打包后会认不出字
for pkg in ("rapidocr_onnxruntime", "onnxruntime", "cv2"):
    try:
        datas += collect_data_files(pkg)
        binaries += collect_dynamic_libs(pkg)
        hidden += collect_submodules(pkg)
    except Exception:
        pass

a = Analysis(
    [str(ROOT / "backend" / "run.py")],
    pathex=[str(ROOT / "backend")],
    binaries=binaries,
    datas=datas,
    hiddenimports=hidden,
    excludes=["tkinter", "matplotlib", "scipy", "pandas", "pytest", "IPython"],
    noarchive=False,
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="StarClerk",
    debug=False,
    strip=False,
    upx=False,
    console=False,  # 桌面版不出黑框，报错都进 logs/app.log
    icon=None,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    name="StarClerk",
)
