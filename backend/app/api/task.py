"""task 分组：托管巡检任务 CRUD + 手动执行（免费最多 5 个，Pro 更多）。"""
from __future__ import annotations

import asyncio
import time
from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from ..db import models as meta
from ..db import sqlite as db
from ..tasks.scheduler import run_task
from .deps import failure

router = APIRouter(prefix="/tasks", tags=["tasks"])


class TaskIn(BaseModel):
    name: str = Field(min_length=1, max_length=60)
    prompt: str = Field(min_length=4, max_length=2000)
    cron_minutes: int = Field(default=60, ge=1, le=10080)
    doc_scope: str = ""
    kind: str = "patrol"


class TaskPatch(BaseModel):
    enabled: bool


class RunOut(BaseModel):
    ok: bool = True
    task_id: str
    result: str
    should_notify: bool
    level: str = "info"
    notice: dict[str, Any] | None = None
    elapsed_ms: int = 0


@router.get("/quota", summary="当前套餐与任务额度")
def quota():
    return meta.plan_info()


@router.get("", summary="任务列表")
def list_tasks():
    return meta.list_tasks()


@router.post("", summary="新建托管任务（校验套餐额度）")
def create(body: TaskIn):
    name, prompt = body.name.strip(), body.prompt.strip()
    if not name or len(prompt) < 4:
        raise HTTPException(400, "任务名和巡检要求都不能为空")
    info = meta.plan_info()
    if info["used"] >= info["limit"]:
        raise HTTPException(
            409,
            f"{info['plan']} 版最多 {info['limit']} 个托管任务，请删除旧任务或升级 Pro",
        )
    return meta.create_task(name, prompt, body.kind, body.cron_minutes, body.doc_scope)


@router.patch("/{tid}", summary="启用/停用任务")
def toggle(tid: str, body: TaskPatch):
    if not meta.get_task(tid):
        raise HTTPException(404, "任务不存在")
    meta.set_task_enabled(tid, body.enabled)
    return meta.get_task(tid)


@router.delete("/{tid}", summary="删除任务")
def remove(tid: str):
    meta.delete_task(tid)
    return {"ok": True}


@router.post("/{tid}/run", response_model=RunOut, summary="立即执行一次")
async def run_now(tid: str):
    task = meta.get_task(tid)
    if not task:
        raise HTTPException(404, "任务不存在")
    # 与调度线程共用抢占逻辑：已在跑或已停用时直接拒绝，避免并发重复执行
    if not meta.claim_task(tid, db.now()):
        raise HTTPException(409, "任务已停用或正在执行")
    started = time.perf_counter()
    try:
        res = await asyncio.to_thread(run_task, task, False)  # 手动执行不弹托盘
    except Exception as e:  # noqa: BLE001
        raise failure("tasks", e) from e
    return RunOut(
        task_id=tid,
        result=str(res.get("result") or ""),
        should_notify=bool(res.get("should_notify")),
        level=str(res.get("level") or "info"),
        notice=res.get("notice"),
        elapsed_ms=int((time.perf_counter() - started) * 1000),
    )
