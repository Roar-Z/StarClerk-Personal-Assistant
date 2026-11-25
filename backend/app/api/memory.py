"""memory 分组：长期记忆的增删查（SQLite 存原文，LanceDB 存向量）。"""
from __future__ import annotations

import asyncio
import logging

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from ..db import models as meta
from ..vector import lancedb_store as vs

router = APIRouter(prefix="/memory", tags=["memory"])
log = logging.getLogger("api.memory")


class MemoryIn(BaseModel):
    content: str = Field(min_length=2, max_length=500)
    kind: str = "fact"


@router.get("", summary="记忆列表")
def list_memories(limit: int = 200):
    return meta.list_memories(max(1, min(limit, 500)))


@router.post("", summary="手动添加记忆")
async def add(body: MemoryIn):
    text = body.content.strip()
    if not text:
        raise HTTPException(400, "内容不能为空")
    m = meta.add_memory(text, body.kind)
    try:
        await asyncio.to_thread(vs.add_memory, m["id"], text, body.kind)
    except Exception as e:  # noqa: BLE001  向量服务没就绪时仍保留文本记忆，召回会退化为最近记忆
        log.warning("记忆向量化失败：%s", e)
        meta.add_error("memory", f"向量化失败：{e}")
        return {**m, "vectorized": False}
    return {**m, "vectorized": True}


@router.delete("/{mid}", summary="删除记忆")
async def remove(mid: str):
    meta.delete_memory(mid)
    try:
        await asyncio.to_thread(vs.delete_memory, mid)
    except Exception:  # noqa: BLE001  向量库里没有就算了
        pass
    return {"ok": True}
