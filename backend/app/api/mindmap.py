"""mindmap 分组：长文档思维导图（Pro），生成后存 md 文件，导出就是把文件发回去。"""
from __future__ import annotations

import asyncio

from fastapi import APIRouter, HTTPException
from fastapi.responses import Response
from pydantic import BaseModel, Field

from .. import mindmap
from .deps import failure

router = APIRouter(prefix="/mindmap", tags=["mindmap"])


class MindIn(BaseModel):
    text: str = Field(default="", max_length=60000)
    doc_id: str = ""
    title: str = Field(default="", max_length=60)


@router.get("", summary="最近生成的导图")
def recent():
    return mindmap.recent()


@router.post("", summary="生成思维导图（Pro）")
async def create(body: MindIn):
    try:
        return await asyncio.to_thread(mindmap.generate, body.text, body.doc_id, body.title)
    except ValueError as e:
        raise HTTPException(400, str(e)) from e
    except Exception as e:  # noqa: BLE001  模型不可用等
        raise failure("mindmap", e) from e


@router.get("/{mid}/export", summary="导出 Markdown 思维导图（Pro）")
def export(mid: str):
    path = mindmap.path_of(mid)
    if not path:
        raise HTTPException(404, "导图不存在，可能没生成成功")
    return Response(
        content=path.read_text(encoding="utf-8"),
        media_type="text/markdown; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="mindmap-{mid}.md"'},
    )
