"""license 分组：本地激活、退回游客、切换低配模式。

三个接口都是本地读写，不联网，激活码错了直接 400。
"""
from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from .. import license, quota
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
    # 游客每小时免费模型剩多少，侧栏和输入框都用它；激活后用自己的模型就不用这个数了
    if data.get("is_guest"):
        data["guest_quota"] = quota.snapshot()
    data["tiers"] = [
        {"name": "guest", "label": "未登录", "desc": "只能对话，用免费模型，会话不保存，不开放知识库/任务/记忆"},
        {
            "name": "free",
            "label": "免费版",
            "desc": "所有功能开放：会话持久化、20 个巡检任务、500 份资料、500 条笔记、思维导图、数据迁移",
        },
    ]
    return data


@router.post("/activate", summary="输入激活码激活（本地校验）")
def activate(body: CodeIn):
    try:
        data = license.activate(body.code)
    except ValueError as e:
        raise HTTPException(400, str(e)) from e
    return data


@router.post("/free", summary="一键免费激活（本地生成激活码）")
def activate_free():
    return license.activate(license.free_code())


@router.delete("", summary="退回未登录")
def reset():
    return license.reset()


@router.post("/perf", summary="低配性能模式开关")
def perf(body: PerfIn):
    license.set_perf(body.on)
    # 工作线程数变了要重启队列，否则还是按旧并发在跑
    runner.stop()
    runner.start()
    return {**license.info(), "scheduler": runner.status()}
