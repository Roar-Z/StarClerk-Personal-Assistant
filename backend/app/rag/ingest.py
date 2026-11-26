"""本地 RAG 入库：文本切块 → 向量化 → LanceDB。

支持纯文本和 PDF；PDF 有文字层直接抽，扫描页走本地 OCR。
workspace 先落在分块上，传空就用 default。
"""
from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from ..db import models as meta
from ..vector import lancedb_store as vs

CHUNK = 600
OVERLAP = 80
SUPPORTED = {".txt", ".md", ".markdown", ".csv", ".log", ".json", ".pdf"}


def split_text(text: str) -> list[str]:
    """按段落聚合到 CHUNK 附近，超长段落硬切，段落间留 OVERLAP 重叠。"""
    text = re.sub(r"\r\n?", "\n", text).strip()
    paras = [p.strip() for p in re.split(r"\n{2,}", text) if p.strip()]
    chunks: list[str] = []
    buf = ""
    for p in paras:
        while len(p) > CHUNK:
            if buf:
                chunks.append(buf)
                buf = ""
            chunks.append(p[:CHUNK])
            p = p[CHUNK - OVERLAP:]
        if len(buf) + len(p) + 2 <= CHUNK:
            buf = f"{buf}\n\n{p}" if buf else p
        else:
            chunks.append(buf)
            buf = (buf[-OVERLAP:] + "\n\n" + p) if OVERLAP else p
    if buf:
        chunks.append(buf)
    return chunks


def ingest_file(
    path: str | Path, doc_id: str | None = None, workspace: str = "", incremental: bool = True
) -> dict[str, Any]:
    p = Path(path)
    if p.suffix.lower() not in SUPPORTED:
        raise ValueError(f"暂不支持 {p.suffix}，可用 pdf / txt / md / csv / log / json")

    extra: dict[str, Any] = {}
    if p.suffix.lower() == ".pdf":
        try:
            from . import pdf as pdf_parser
        except ImportError as e:  # noqa: BLE001
            raise ValueError("这台机器还没装 PDF 解析库 pymupdf，装一下再传") from e
        hit = pdf_parser.extract(p)
        text = hit["text"]
        extra = {"pages": hit["pages"], "ocr_pages": hit["ocr_pages"]}
    else:
        text = p.read_text(encoding="utf-8", errors="ignore")

    doc_id = doc_id or f"doc-{meta.new_id()}"
    chunks = split_text(text)
    n = vs.add_document(doc_id, p.name, chunks, workspace)
    return {
        "doc_id": doc_id,
        "source": p.name,
        "chunks": n,
        "total_chunks": len(chunks),
        "workspace": workspace or vs.DEFAULT_WS,
        "incremental": bool(incremental),
        **extra,
    }


def ingest_text(text: str, source: str = "粘贴文本", workspace: str = "") -> dict[str, Any]:
    doc_id = f"doc-{meta.new_id()}"
    chunks = split_text(text)
    n = vs.add_document(doc_id, source, chunks, workspace)
    return {
        "doc_id": doc_id,
        "source": source,
        "chunks": n,
        "total_chunks": len(chunks),
        "workspace": workspace or vs.DEFAULT_WS,
    }
