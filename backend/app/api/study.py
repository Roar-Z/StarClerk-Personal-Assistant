"""学习空间接口：学习通扫码登录、总开关、状态与日志、课表导出。

作业同步没有手动刷新入口——只由首次登录和每天三个固定点触发。
"""
from __future__ import annotations

import time
from typing import Any

from fastapi import APIRouter, HTTPException
from fastapi.responses import Response
from pydantic import BaseModel, Field

from .. import access
from ..study import chaoxing, schedule, store
from ..tasks.study_sync import study_sync

router = APIRouter(prefix="/study", tags=["study"])


class TermIn(BaseModel):
    date: str = Field(pattern=r"^\d{4}-\d{2}-\d{2}$")


@router.get("/status", summary="学习空间状态")
def status():
    access.require("study")
    return {
        "enabled": store.enabled(),
        "cookie": store.cookie_info(),
        "last_sync": store.last_sync(),
        "logs": store.logs()[:50],
        "slots": ["12:40", "19:00", "22:00"],
        "term_start": schedule.term_start(),
        "schedule_can_fetch": schedule.can_fetch(),
        "schedule_cached": bool(schedule.cached()),
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
    store.set_cookie("")  # 退出登录，下次要重新扫码
    store.add_log("off", "用户关闭总开关，已退出学习通，重新开启需再次扫码")
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


@router.get("/logs", summary="学习通同步日志")
def get_logs(limit: int = 50):
    access.require("study")
    return {"items": store.logs()[: max(1, min(limit, 300))]}


# ---------------- 课表日历导出 ----------------
@router.get("/term", summary="读学期开始日期")
def get_term():
    access.require("study")
    return {"date": schedule.term_start()}


@router.post("/term", summary="保存学期第一周周一的日期")
def save_term(body: TermIn):
    access.require("study")
    schedule.set_term_start(body.date)
    return {"ok": True, "date": body.date}


@router.get("/schedule/preview", summary="预览课表（点导出才读，有间隔限制）")
def schedule_preview(weeks: int = 20, force: bool = False):
    access.require("study")
    try:
        items = schedule.fetch(weeks, force)
    except schedule.TooFrequent as e:
        raise HTTPException(429, str(e)) from e
    except chaoxing.SessionExpired as e:
        raise HTTPException(401, str(e)) from e
    except ValueError as e:
        raise HTTPException(400, str(e)) from e
    except Exception as e:  # noqa: BLE001
        raise HTTPException(502, f"读课表失败：{e}") from e
    store.add_log("schedule", "预览课表", new=len(items))
    return {"items": items, "count": len(items), "can_fetch": schedule.can_fetch(), "cached": bool(schedule.cached())}


@router.post("/schedule/cache", summary="清掉课表缓存，下次重新读")
def clear_schedule_cache():
    access.require("study")
    schedule.clear_cache()
    return {"ok": True}


@router.get("/schedule/export", summary="导出课表日历（.ics）")
def schedule_export(weeks: int = 20):
    access.require("study")
    start = schedule.term_start()
    if not start:
        raise HTTPException(400, "请先填学期第一周周一的日期")
    try:
        items = schedule.fetch(weeks)
    except schedule.TooFrequent as e:
        raise HTTPException(429, str(e)) from e
    except chaoxing.SessionExpired as e:
        raise HTTPException(401, str(e)) from e
    except ValueError as e:
        raise HTTPException(400, str(e)) from e
    except Exception as e:  # noqa: BLE001
        raise HTTPException(502, f"读课表失败：{e}") from e
    ics = schedule.to_ics(items, start)
    store.add_log("schedule", "导出课表日历", new=len(items))
    name = f"schedule-{time.strftime('%Y%m%d')}.ics"
    return Response(
        content="\ufeff" + ics,
        media_type="text/calendar; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{name}"'},
    )
