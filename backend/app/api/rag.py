"""rag 分组：本地知识库导入/检索/删除（SQLite 只做元数据，正文在 LanceDB）。"""
from __future__ import annotations

import asyncio
import shutil
from pathlib import Path

from fastapi import APIRouter, File, HTTPException, UploadFile
from pydantic import BaseModel, Field

from ..config import settings
from ..rag import ingest
from ..vector import lancedb_store as vs
from .deps import failure

router = APIRouter(prefix="/rag", tags=["rag"])


class TextIn(BaseModel):
    text: str = Field(min_length=10, max_length=200000)
    source: str = Field(default="粘贴文本", max_length=120)


@router.post("/upload", summary="上传文件入库（txt/md/csv/log/json）")
async def upload(file: UploadFile = File(...)):
    name = Path(file.filename or "upload.txt").name  # 去掉路径，防目录穿越
    dest = Path(settings.upload_path) / name
    with dest.open("wb") as f:
        shutil.copyfileobj(file.file, f)
    try:
        return await asyncio.to_thread(ingest.ingest_file, dest)
    except ValueError as e:
        raise HTTPException(400, str(e)) from e
    except Exception as e:  # noqa: BLE001  向量服务未就绪等
        raise failure("rag", e) from e


@router.post("/text", summary="粘贴文本入库")
async def add_text(body: TextIn):
    try:
        return await asyncio.to_thread(ingest.ingest_text, body.text, body.source)
    except Exception as e:  # noqa: BLE001
        raise failure("rag", e) from e


@router.get("/stats", summary="知识库统计")
async def stats():
    return await asyncio.to_thread(vs.stats)


@router.get("/documents", summary="已入库文档")
async def documents():
    return await asyncio.to_thread(vs.list_documents)


@router.get("/search", summary="检索（排查用，不走模型）")
async def search(q: str, top_k: int = 5, doc_scope: str = ""):
    if not q.strip():
        raise HTTPException(400, "q 不能为空")
    try:
        return await asyncio.to_thread(vs.search_documents, q, max(1, min(top_k, 10)), doc_scope)
    except Exception as e:  # noqa: BLE001
        raise failure("rag", e) from e


@router.delete("/documents/{doc_id}", summary="删除文档")
async def remove(doc_id: str):
    await asyncio.to_thread(vs.delete_document, doc_id)
    return {"ok": True}
