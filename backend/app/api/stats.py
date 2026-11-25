"""stats 分组：运行概览、token 消耗（落库的按天统计）、异常日志。"""
from __future__ import annotations

import asyncio

from fastapi import APIRouter

from ..db import models as meta
from ..db import sqlite as db
from ..llm import client
from ..vector import lancedb_store as vs

router = APIRouter(prefix="/stats", tags=["stats"])


@router.get("/overview", summary="运行概览")
async def overview():
    now = db.now()
    tasks = meta.list_tasks()
    return {
        "plan": meta.plan_info(),
        "tasks": {
            "total": len(tasks),
            "enabled": sum(1 for t in tasks if t.get("enabled")),
            "due": len(meta.due_tasks(now)),
        },
        "knowledge": await asyncio.to_thread(vs.stats),
        "usage_24h": meta.usage_summary(1)["totals"],
        "errors_24h": meta.count_errors(now - 86400),
        "process_usage": client.stats(),  # 本进程累计，与落库口径区分
    }


@router.get("/usage", summary="token 消耗（按天/场景/模型）")
def usage(days: int = 7):
    return meta.usage_summary(max(1, min(days, 90)))


@router.get("/errors", summary="最近异常")
def errors(limit: int = 30):
    return meta.list_errors(max(1, min(limit, 200)))
