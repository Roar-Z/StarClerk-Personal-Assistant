"""license 分组：本机登录、退出、切换低配模式。

都是本地读写，不联网，也没有账号密码。
"""
from __future__ import annotations

from fastapi import APIRouter
from pydantic import BaseModel

from .. import license, quota
from ..llm import client as llm
from ..tasks.scheduler import runner

router = APIRouter(prefix="/license", tags=["license"])


class PerfIn(BaseModel):
    on: bool


@router.get("", summary="当前登录状态与运行状态")
def info():
    data = license.info()
    data["llm"] = llm.gate_stats()
    data["scheduler"] = runner.status()
    # 未登录每小时免费模型剩多少，输入框下面用它；登录后用自己的模型就不用这个数了
    if data.get("is_guest"):
        data["guest_quota"] = quota.snapshot()
    data["tiers"] = [
        {"name": "guest", "label": "未登录", "desc": "只能对话，用免费模型，会话不保存，不开放知识库/任务/记忆"},
        {
            "name": "free",
            "label": "已登录",
            "desc": "登录后所有功能开放：会话持久化、20 个巡检任务、500 份资料、500 条笔记、思维导图、数据迁移",
        },
    ]
    return data


@router.post("/login", summary="本机登录")
def login():
    return license.login()


@router.post("/logout", summary="退出登录")
def logout():
    return license.logout()


@router.post("/perf", summary="低配性能模式开关")
def perf(body: PerfIn):
    license.set_perf(body.on)
    # 工作线程数变了要重启队列，否则还是按旧并发在跑
    runner.stop()
    runner.start()
    return {**license.info(), "scheduler": runner.status()}
