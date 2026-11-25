"""task 分组：托管巡检任务 CRUD + 手动执行 + 巡检日志。

额度按档位算：游客 0 个，免费 5 个，Pro 20 个（见 access.LIMITS）。
"""
from __future__ import annotations

import asyncio
import csv
import io
import time
from typing import Any

from fastapi import APIRouter, HTTPException
from fastapi.responses import Response
from pydantic import BaseModel, Field

from .. import access, license
from ..db import models as meta
from ..db import sqlite as db
from ..tasks.scheduler import runner
from ..tasks.worker import run_task
from .deps import failure

router = APIRouter(prefix="/tasks", tags=["tasks"])


class TaskIn(BaseModel):
    name: str = Field(min_length=1, max_length=60)
    prompt: str = Field(min_length=4, max_length=2000)
    cron_minutes: int = Field(default=60, ge=1, le=10080)
    doc_scope: str = ""
    workspace: str = ""
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


@router.get("/quota", summary="当前档位与任务额度")
def quota():
    info = meta.plan_info()
    info["service"] = runner.status()
    return info


@router.get("/logs", summary="巡检历史（免费版起，Pro 可导出）")
def logs(task_id: str = "", limit: int = 50):
    rows = meta.list_task_logs(task_id, max(1, min(limit, 200)))
    for r in rows:
        r["ok"] = bool(r["ok"])
    return {"items": rows, "total": meta.count_task_logs(task_id), "exportable": license.tier() == "pro"}


@router.get("/logs/export", summary="导出巡检日志 CSV（Pro）")
def export_logs(task_id: str = ""):
    access.require("log_export")
    rows = meta.list_task_logs(task_id, 500)
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(["时间", "任务", "结果", "级别", "耗时(ms)", "内容"])
    for r in rows:
        w.writerow(
            [
                time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(float(r["created_at"]))),
                r["name"],
                "成功" if r["ok"] else "失败",
                r["level"],
                r["elapsed_ms"],
                str(r["result"]).replace("\n", " "),
            ]
        )
    name = f"patrol-logs-{time.strftime('%Y%m%d')}.csv"
    return Response(
        content="\ufeff" + buf.getvalue(),  # 带 BOM，Excel 打开中文不乱码
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{name}"'},
    )


@router.get("", summary="任务列表")
def list_tasks():
    return meta.list_tasks()


@router.post("", summary="新建托管任务（校验档位额度）")
def create(body: TaskIn):
    name, prompt = body.name.strip(), body.prompt.strip()
    if not name or len(prompt) < 4:
        raise HTTPException(400, "任务名和巡检要求都不能为空")
    access.check_limit("tasks", len(meta.list_tasks()))
    return meta.create_task(
        name, prompt, body.kind, body.cron_minutes, body.doc_scope, body.workspace
    )


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
        ok=bool(res.get("ok", True)),
        result=str(res.get("result") or ""),
        should_notify=bool(res.get("should_notify")),
        level=str(res.get("level") or "info"),
        notice=res.get("notice"),
        elapsed_ms=int((time.perf_counter() - started) * 1000),
    )
