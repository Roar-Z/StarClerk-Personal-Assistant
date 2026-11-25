"""license 分组：本地激活、退回游客、切换低配模式。

三个接口都是本地读写，不联网，激活码错了直接 400。
"""
from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from .. import license
from ..llm import client as llm
from ..tasks.scheduler import runner

router = APIRouter(prefix="/license", tags=["license"])


class CodeIn(BaseModel):
    code: str = Field(min_length=8, max_length=64)


class PerfIn(BaseModel):
    on: bool


@router.get("", summary="当前档位与运行状态")
def info():
    data = license.info()
    data["llm"] = llm.gate_stats()
    data["scheduler"] = runner.status()
    data["tiers"] = [
        {"name": "guest", "label": "游客", "desc": "对话可用，会话不保存，不开放知识库/任务/记忆"},
        {"name": "free", "label": "免费版", "desc": "会话持久化、轻量知识库、5 个巡检任务、基础记忆"},
        {"name": "pro", "label": "Pro 版", "desc": "思维导图、多工作区、票据抽取、记忆分组、日志导出"},
    ]
    return data


@router.post("/activate", summary="输入激活码激活（本地校验）")
def activate(body: CodeIn):
    try:
        data = license.activate(body.code)
    except ValueError as e:
        raise HTTPException(400, str(e)) from e
    return data


@router.delete("", summary="退回游客模式")
def reset():
    return license.reset()


@router.post("/perf", summary="低配性能模式开关")
def perf(body: PerfIn):
    license.set_perf(body.on)
    # 工作线程数变了要重启队列，否则还是按旧并发在跑
    runner.stop()
    runner.start()
    return {**license.info(), "scheduler": runner.status()}
