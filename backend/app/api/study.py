"""学习空间接口：学习通扫码登录、总开关、考试时段、状态与日志。

没有手动刷新入口——同步只由首次登录和每天三个固定点触发。
"""
from __future__ import annotations

import time
from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from .. import access
from ..study import chaoxing, store
from ..tasks.study_sync import study_sync

router = APIRouter(prefix="/study", tags=["study"])


class ExamIn(BaseModel):
    name: str = Field(default="考试", max_length=60)
    start: float
    end: float


class ExamsIn(BaseModel):
    items: list[ExamIn] = Field(default_factory=list, max_length=50)


@router.get("/status", summary="学习空间状态")
def status():
    access.require("study")
    return {
        "enabled": store.enabled(),
        "cookie": store.cookie_info(),
        "exams": store.exams(),
        "last_sync": store.last_sync(),
        "logs": store.logs()[:50],
        "slots": ["12:40", "19:00", "22:00"],
    }


@router.post("/enable", summary="开启定时模式")
def enable():
    access.require("study")
    store.set_enabled(True)
    store.add_log("on", "用户开启每日三时段定时模式")
    return {"ok": True, "enabled": True}


@router.post("/disable", summary="停止访问学习通（总开关）")
def disable():
    access.require("study")
    store.set_enabled(False)
    store.add_log("off", "用户关闭总开关，停止全部自动请求")
    return {"ok": True, "enabled": False}


@router.post("/qr/start", summary="取扫码登录二维码")
def qr_start():
    access.require("study")
    try:
        return chaoxing.start_qr()
    except ValueError as e:
        raise HTTPException(400, str(e)) from e
    except chaoxing.SessionExpired as e:
        raise HTTPException(401, str(e)) from e
    except Exception as e:  # noqa: BLE001
        raise HTTPException(502, f"取二维码失败：{e}") from e


@router.post("/qr/check", summary="轮询扫码结果")
def qr_check(key: str):
    access.require("study")
    try:
        hit = chaoxing.poll_qr(key)
    except ValueError as e:
        raise HTTPException(400, str(e)) from e
    except Exception as e:  # noqa: BLE001
        raise HTTPException(502, f"查扫码状态失败：{e}") from e
    if hit.get("status") == "ok":
        store.add_log("login", "扫码登录成功")
        # 首次登录即时拉一次作业，不受定时任务限制
        if store.enabled():
            study_sync.sync_now("首次登录")
    return hit


@router.post("/logout", summary="清掉学习通 cookie")
def logout():
    access.require("study")
    store.set_cookie("")
    store.add_log("logout", "用户清除学习通会话")
    return {"ok": True}


@router.get("/exams", summary="考试时段列表")
def get_exams():
    access.require("study")
    return {"items": store.exams()}


@router.post("/exams", summary="保存考试时段（强制保护，无开关）")
def save_exams(body: ExamsIn):
    access.require("study")
    items = [
        {"name": x.name.strip() or "考试", "start": float(x.start), "end": float(x.end)}
        for x in body.items
        if x.end > x.start > 0
    ]
    items.sort(key=lambda x: x["start"])
    store.set_exams(items)
    store.add_log("exam", f"更新考试时段 {len(items)} 段")
    return {"ok": True, "items": items}


@router.get("/logs", summary="学习通同步日志")
def get_logs(limit: int = 50):
    access.require("study")
    return {"items": store.logs()[: max(1, min(limit, 300))]}
