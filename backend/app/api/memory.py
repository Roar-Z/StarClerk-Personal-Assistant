"""memory 分组：长期记忆的增删查（SQLite 存原文，LanceDB 存向量）。

免费版：查看、手动添加、单条删除；Pro 才有分组和备份导入导出。
"""
from __future__ import annotations

import asyncio
import json
import logging
import time
from typing import Any

from fastapi import APIRouter, HTTPException
from fastapi.responses import Response
from pydantic import BaseModel, Field

from .. import access
from ..db import models as meta
from ..db import sqlite as db
from ..vector import lancedb_store as vs

router = APIRouter(prefix="/memory", tags=["memory"])
log = logging.getLogger("api.memory")


class MemoryIn(BaseModel):
    content: str = Field(min_length=2, max_length=500)
    kind: str = "fact"
    group: str = ""


class GroupIn(BaseModel):
    group: str = Field(max_length=40)


@router.get("", summary="记忆列表")
def list_memories(limit: int = 200, group: str = ""):
    return meta.list_memories(max(1, min(limit, 500)), group)


@router.post("", summary="手动添加记忆（受档位条数限制）")
async def add(body: MemoryIn):
    text = body.content.strip()
    if not text:
        raise HTTPException(400, "内容不能为空")
    access.check_limit("memories", meta.count_memories())
    m = meta.add_memory(text, body.kind, group_name=body.group)
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


# ---------------- Pro：分组 ----------------
@router.get("/groups", summary="记忆分组（Pro）")
def groups():
    rows = meta.memory_groups()
    for r in rows:
        r["name"] = r["name"] or "未分组"
    return {"items": rows, "ungrouped": meta.count_memories("") - sum(r["n"] for r in rows if r["name"] != "未分组")}


@router.patch("/{mid}/group", summary="给记忆分组（Pro）")
def move_group(mid: str, body: GroupIn):
    access.require("memory_group")  # 路径在 /memory 下，中间件按功能分不出来
    if not db.row("SELECT id FROM memories WHERE id=?", (mid,)):
        raise HTTPException(404, "记忆不存在")
    meta.set_memory_group(mid, body.group.strip())
    return {"ok": True, "group": body.group.strip() or "未分组"}


# ---------------- Pro：备份 ----------------
@router.get("/backup", summary="导出记忆备份（Pro）")
def backup():
    rows = [
        {"content": r["content"], "kind": r["kind"], "group": r["group_name"]}
        for r in meta.list_memories(2000)
    ]
    payload = {"exported_at": time.strftime("%Y-%m-%d %H:%M:%S"), "count": len(rows), "items": rows}
    return Response(
        content=json.dumps(payload, ensure_ascii=False, indent=2),
        media_type="application/json; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="memories-{time.strftime("%Y%m%d")}.json"'},
    )


@router.post("/backup", summary="导入记忆备份（Pro，按内容去重）")
async def restore(items: list[dict[str, Any]]):
    access.check_limit("memories", meta.count_memories())
    have = {r["content"] for r in meta.list_memories(2000)}
    added = 0
    for it in items[:200]:
        text = str(it.get("content") or "").strip()
        if len(text) < 2 or text in have:
            continue
        m = meta.add_memory(text, str(it.get("kind") or "fact"), group_name=str(it.get("group") or ""))
        have.add(text)
        added += 1
        try:
            await asyncio.to_thread(vs.add_memory, m["id"], text, m["kind"])
        except Exception:  # noqa: BLE001  向量失败不影响原文
            pass
    return {"ok": True, "added": added, "skipped": len(items) - added}


# ---------------- Pro：画像 / 自动归类 / 定期总结 ----------------
@router.get("/profile", summary="画像与分组概览（Pro）")
def profile():
    return meta.memory_profile()


@router.post("/organize", summary="给没归组的记忆自动起组（Pro）")
async def organize():
    """按 kind 先分堆，再让模型给每堆起个短名字。逐条让模型归类太烧 token，也不准。"""
    from ..llm import client

    loose = [r for r in meta.list_memories(300) if not (r.get("group_name") or "").strip()]
    if not loose:
        return {"ok": True, "moved": 0, "groups": []}

    buckets: dict[str, list[dict[str, Any]]] = {}
    for r in loose:
        buckets.setdefault(r.get("kind") or "fact", []).append(r)

    moved, groups = 0, []
    for kind, rows in buckets.items():
        sample = "\n".join(f"- {r['content'][:60]}" for r in rows[:12])
        try:
            res = await asyncio.to_thread(
                client.complete,
                [{"role": "user", "content": f"下面是用户的{kind}类记忆，起一个 2-4 个字的中文分组名，"
                                            f"只回名字，不要标点。\n{sample}"}],
                temperature=0.2,
                scope="memory",
            )
            name = res.content.strip().strip("「」“”\"'。 ") or kind
        except Exception:  # noqa: BLE001  模型不给力就退回固定名字
            name = {"fact": "事实", "preference": "偏好", "todo": "待办", "summary": "总结"}.get(kind, "其他")
        name = name[:8]
        for r in rows:
            meta.set_memory_group(r["id"], name)
            moved += 1
        groups.append({"name": name, "n": len(rows)})
    return {"ok": True, "moved": moved, "groups": groups}


@router.post("/summarize", summary="把现有记忆总结成一条（Pro）")
async def summarize():
    from ..llm import client

    rows = meta.list_memories(120)
    if not rows:
        return {"ok": False, "text": "还没有记忆可总结"}
    body = "\n".join(f"- [{r.get('group_name') or r.get('kind')}] {r['content']}" for r in rows)
    try:
        res = await asyncio.to_thread(
            client.complete,
            [{"role": "user", "content": "下面是我的长期记忆。用 200 字以内归纳一下我现在在做什么、"
                                        "关心什么、有什么没完成的，用第二人称写，别分点。\n" + body}],
            temperature=0.3,
            scope="memory",
        )
    except Exception as e:  # noqa: BLE001
        raise HTTPException(502, f"总结失败：{str(e)[:150]}") from e
    text = res.content.strip()
    if text:
        meta.add_memory(text[:600], "summary")
    return {"ok": True, "text": text}
