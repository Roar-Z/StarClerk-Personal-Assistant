"""专注番茄钟接口：开始、暂停、继续、结束、统计。"""
from __future__ import annotations

from fastapi import APIRouter
from pydantic import BaseModel, Field

from .. import access, focus

router = APIRouter(prefix="/focus", tags=["focus"])


class StartIn(BaseModel):
    minutes: int = Field(default=focus.FOCUS_MIN, ge=1, le=180)
    mode: str = Field(default="focus", pattern="^(focus|short|long)$")


@router.get("/status", summary="专注状态 + 统计")
def status(days: int = 7):
    access.require("focus")
    return {"session": focus.session(), "stats": focus.stats(days)}


@router.post("/start", summary="开始专注或休息")
def start(body: StartIn):
    access.require("focus")
    return {"ok": True, "session": focus.start(body.minutes, body.mode)}


@router.post("/pause", summary="暂停")
def pause():
    access.require("focus")
    return {"ok": True, "session": focus.pause()}


@router.post("/resume", summary="继续")
def resume():
    access.require("focus")
    return {"ok": True, "session": focus.resume()}


@router.post("/stop", summary="结束当前段")
def stop():
    access.require("focus")
    return {"ok": True, "session": focus.stop()}


@router.get("/stats", summary="专注时长统计")
def get_stats(days: int = 7):
    access.require("focus")
    return focus.stats(days)
