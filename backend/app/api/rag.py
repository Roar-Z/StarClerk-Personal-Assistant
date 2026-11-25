"""rag 分组：本地知识库导入/检索/删除（SQLite 只做元数据，正文在 LanceDB）。

登录后：单文档上传（最多 500 份）、多工作区、批量导入导出、票据抽取都开放。
越权由 access 中间件按路径拦，这里只管额度和业务。
"""
from __future__ import annotations

import asyncio
import csv
import io
import json
import shutil
import time
from pathlib import Path
from typing import Any

from fastapi import APIRouter, File, HTTPException, UploadFile
from fastapi.responses import Response
from pydantic import BaseModel, Field

from .. import access
from ..config import settings
from ..llm import client
from ..rag import ingest
from ..vector import lancedb_store as vs
from .deps import failure

router = APIRouter(prefix="/rag", tags=["rag"])


class TextIn(BaseModel):
    text: str = Field(min_length=10, max_length=200000)
    source: str = Field(default="粘贴文本", max_length=120)
    workspace: str = ""


class MoveIn(BaseModel):
    workspace: str = Field(max_length=40)


class ExtractIn(BaseModel):
    doc_id: str


def _guard_count(doc_id: str = "") -> None:
    """新增文档才查上限，同一个 doc 重新导入算增量，不占名额。"""
    docs = vs.list_documents()
    if doc_id and any(d["doc_id"] == doc_id for d in docs):
        return
    access.check_limit("docs", len(docs))


@router.post("/upload", summary="上传文件入库（txt/md/csv/log/json）")
async def upload(
    file: UploadFile = File(...), workspace: str = "", doc_id: str = ""
):
    name = Path(file.filename or "upload.txt").name  # 去掉路径，防目录穿越
    _guard_count(doc_id)
    dest = Path(settings.upload_path) / name
    with dest.open("wb") as f:
        shutil.copyfileobj(file.file, f)
    try:
        return await asyncio.to_thread(
            ingest.ingest_file, dest, doc_id or None, workspace
        )
    except ValueError as e:
        raise HTTPException(400, str(e)) from e
    except Exception as e:  # noqa: BLE001  向量服务未就绪等
        raise failure("rag", e) from e


@router.post("/text", summary="粘贴文本入库")
async def add_text(body: TextIn):
    _guard_count()
    try:
        return await asyncio.to_thread(ingest.ingest_text, body.text, body.source, body.workspace)
    except Exception as e:  # noqa: BLE001
        raise failure("rag", e) from e


@router.get("/stats", summary="知识库统计")
async def stats():
    return await asyncio.to_thread(vs.stats)


@router.get("/documents", summary="已入库文档")
async def documents(workspace: str = ""):
    return await asyncio.to_thread(vs.list_documents, workspace)


@router.get("/search", summary="检索（排查用，不走模型）")
async def search(q: str, top_k: int = 5, doc_scope: str = "", workspace: str = ""):
    if not q.strip():
        raise HTTPException(400, "q 不能为空")
    try:
        return await asyncio.to_thread(
            vs.search_documents, q, max(1, min(top_k, 10)), doc_scope, workspace
        )
    except Exception as e:  # noqa: BLE001
        raise failure("rag", e) from e


@router.delete("/documents/{doc_id}", summary="删除文档")
async def remove(doc_id: str):
    await asyncio.to_thread(vs.delete_document, doc_id)
    return {"ok": True}


# ----------------多工作区 ----------------
@router.get("/workspaces", summary="工作区列表")
def workspaces():
    return {"items": vs.list_workspaces(), "default": vs.DEFAULT_WS}


@router.patch("/documents/{doc_id}/workspace", summary="移动文档到工作区")
async def move(doc_id: str, body: MoveIn):
    access.require("workspace")  # 路径挂在 documents 下，中间件认不出，这里补一刀
    name = body.workspace.strip() or vs.DEFAULT_WS
    n = await asyncio.to_thread(vs.move_document, doc_id, name)
    if not n:
        raise HTTPException(404, "文档不存在")
    return {"ok": True, "workspace": name, "chunks": n}


@router.delete("/workspaces/{name}", summary="删工作区（文档退回 default）")
def drop_workspace(name: str):
    if name == vs.DEFAULT_WS:
        raise HTTPException(400, "默认工作区不能删")
    moved = 0
    for d in vs.list_documents(name):
        moved += vs.move_document(d["doc_id"], vs.DEFAULT_WS)
    return {"ok": True, "moved": moved}


# ----------------批量导入导出 ----------------
@router.post("/batch", summary="批量导入")
async def batch_upload(files: list[UploadFile] = File(...), workspace: str = ""):
    ok, failed = [], []
    for f in files:
        name = Path(f.filename or "upload.txt").name
        dest = Path(settings.upload_path) / name
        try:
            _guard_count()
            with dest.open("wb") as fh:
                shutil.copyfileobj(f.file, fh)
            ok.append(await asyncio.to_thread(ingest.ingest_file, dest, None, workspace))
        except Exception as e:  # noqa: BLE001  单个失败不影响整批
            failed.append({"source": name, "error": str(e)[:120]})
    return {"ok": ok, "failed": failed, "workspace": workspace or vs.DEFAULT_WS}


@router.get("/batch/export", summary="导出文档清单 CSV")
def batch_export():
    rows = vs.list_documents()
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(["doc_id", "文件名", "工作区", "分块数"])
    for d in rows:
        w.writerow([d["doc_id"], d["source"], d["workspace"], d["chunks"]])
    name = f"documents-{time.strftime('%Y%m%d')}.csv"
    return Response(
        content="\ufeff" + buf.getvalue(),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{name}"'},
    )


# ----------------票据轻结构化抽取 ----------------
_EXTRACT_PROMPT = """从下面这段票据/发票文字里抽字段，只回 JSON，不要解释：
{"invoice_no":"", "date":"", "amount":"", "tax":"", "seller":"", "buyer":"", "items":[]}
抽不到的字段填空字符串。文字：
{text}"""


@router.post("/extract", summary="票据字段抽取")
def extract(body: ExtractIn):
    text = vs.document_text(body.doc_id, 6000)
    if len(text) < 10:
        raise HTTPException(404, "文档不存在或没有正文")
    res = client.complete(
        [{"role": "user", "content": _EXTRACT_PROMPT.format(text=text)}],
        temperature=0.1,
        scope="extract",
    )
    raw = res.content.strip().removeprefix("```json").removeprefix("```").removesuffix("```").strip()
    try:
        data: dict[str, Any] = json.loads(raw)
    except ValueError as e:
        raise HTTPException(422, "模型没按 JSON 返回，稍后再试一次") from e
    return {"doc_id": body.doc_id, "fields": data, "model": res.model}


# ----------------批量摘要 / 翻译 / 抽表格 ----------------
_BATCH_PROMPT = {
    "summary": "把下面这份文档压成 5 条以内的要点，一行一条，别写开场白和总结句。\n\n{text}",
    "translate": "把下面内容翻译成{lang}，术语和数字保持原样，只输出译文。\n\n{text}",
    "table": "把文中所有表格转成 CSV，字段里带逗号的用双引号包住。只输出 CSV，"
    "一个表格都没有就输出一行「没有表格」。\n\n{text}",
}


class BatchAiIn(BaseModel):
    doc_ids: list[str] = Field(min_length=1, max_length=10)
    action: str = Field(default="summary", pattern="^(summary|translate|table)$")
    lang: str = "中文"


@router.post("/batch-ai", summary="批量摘要 / 翻译 / 抽表格")
def batch_ai(body: BatchAiIn):
    """一次最多 10 份，串着跑。并发开满容易撞上游限流，慢一点反而稳。"""
    sources = {d.get("doc_id"): d.get("source", "") for d in vs.list_documents()}
    items: list[dict[str, Any]] = []
    csv_parts: list[str] = []
    for doc_id in body.doc_ids:
        text = vs.document_text(doc_id, 8000)
        source = sources.get(doc_id, "")
        if len(text) < 10:
            items.append({"doc_id": doc_id, "source": source, "ok": False, "text": "文档不存在或没有正文"})
            continue
        prompt = _BATCH_PROMPT[body.action].format(text=text, lang=body.lang)
        try:
            res = client.complete([{"role": "user", "content": prompt}], temperature=0.2, scope="batch")
            content = res.content.strip()
            items.append({"doc_id": doc_id, "source": source, "ok": True, "text": content})
            if body.action == "table" and "没有表格" not in content:
                csv_parts.append(f"# {source}\n{content}")
        except Exception as e:  # noqa: BLE001  单份失败不影响后面
            items.append({"doc_id": doc_id, "source": source, "ok": False, "text": str(e)[:200]})
    return {
        "action": body.action,
        "items": items,
        "csv": "\n\n".join(csv_parts),
        "ok_count": sum(1 for i in items if i["ok"]),
    }
