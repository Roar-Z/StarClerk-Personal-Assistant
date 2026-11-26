"""PDF 解析：文本层优先，扫描页走本地 OCR。

企业里常用的做法，RAGFlow / Dify 都是这套：
先看这页有没有文字层，有就直接抽；没有（扫描件）才渲染成图用 OCR 认。
全程本机处理，不联网。页码留在正文里，方便对话时引用到第几页。
"""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

log = logging.getLogger("pdf")

MIN_TEXT = 20        # 一页不到 20 个字当扫描页，走 OCR
MAX_PAGES = 200      # 太多页直接拦，别把内存和 CPU 吃满
ZOOM = 2.0           # 渲染倍率，2 倍约 144dpi，ocr 够用又不太慢


def extract(path: str | Path) -> dict[str, Any]:
    """返回整本文档的文字，以及一共几页、几页走了 OCR。"""
    import fitz  # PyMuPDF，按需导入，不装也不影响其它功能

    doc = fitz.open(path)
    try:
        if doc.page_count > MAX_PAGES:
            raise ValueError(f"这份 PDF 有 {doc.page_count} 页，超过 {MAX_PAGES} 页上限，先拆开再传")
        parts: list[str] = []
        ocr_pages = 0
        for i, page in enumerate(doc):
            text = page.get_text("text").strip()
            if len(text) < MIN_TEXT:
                text = _ocr_page(page)
                if text:
                    ocr_pages += 1
            if text:
                parts.append(f"【第{i + 1}页】\n{text}")
        return {"text": "\n\n".join(parts), "pages": doc.page_count, "ocr_pages": ocr_pages}
    finally:
        doc.close()


def _ocr_page(page: Any) -> str:
    """把一页渲染成图，丢给本地 OCR。"""
    import cv2
    import numpy as np

    from .. import ocr

    pix = page.get_pixmap(matrix=fitz_matrix(), alpha=False)
    img = np.frombuffer(pix.samples, dtype=np.uint8).reshape(pix.height, pix.width, pix.n)
    if pix.n == 4:
        img = cv2.cvtColor(img, cv2.COLOR_RGBA2BGR)
    elif pix.n == 3:
        img = cv2.cvtColor(img, cv2.COLOR_RGB2BGR)
    return str(ocr.recognize_image(img).get("text") or "").strip()


def fitz_matrix() -> Any:
    import fitz

    return fitz.Matrix(ZOOM, ZOOM)
