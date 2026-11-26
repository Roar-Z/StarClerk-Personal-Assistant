"""教务课表导入接口：只做广东科技学院。

登录在独立浏览器窗口里由用户自己完成；这里只接收当前页 HTML，
在本机解析、预览、保存、导出。不上传、不碰登录接口。
"""
from __future__ import annotations

import time

from fastapi import APIRouter, HTTPException
from fastapi.responses import Response
from pydantic import BaseModel, Field

from .. import access, license
from ..eas import ics as ics_mod
from ..eas import parser as eas_parser
from ..eas import store as eas_store
from ..study import schedule as term_store

router = APIRouter(prefix="/eas", tags=["eas"])


class HtmlIn(BaseModel):
    html: str = Field(default="", max_length=8_000_000)


class CoursesIn(BaseModel):
    items: list[dict] = Field(default_factory=list, max_length=500)


class DateIn(BaseModel):
    date: str = Field(pattern=r"^\d{4}-\d{2}-\d{2}$")


@router.get("/info", summary="教务课表状态")
def info():
    access.require("eas")
    return {
        "school": "广东科技学院",
        "portal": "https://portal.gdust.edu.cn",
        "saved": eas_store.info(),
        "term_start": term_store.term_start(),
    }


@router.post("/preview", summary="解析当前页 HTML，预览课表")
def preview(body: HtmlIn):
    access.require("eas")
    if not body.html.strip():
        raise HTTPException(400, "没拿到页面内容，先登录门户并打开课表页")
    items = eas_parser.parse(body.html)
    return {"items": items, "count": len(items)}


@router.post("/save", summary="保存预览确认后的课表")
def save(body: CoursesIn):
    access.require("eas")
    if license.is_guest():
        raise HTTPException(403, "登录后才能保存课表")
    eas_store.save(body.items)
    return {"ok": True, "count": len(body.items)}


@router.get("/courses", summary="已保存的课表")
def get_courses():
    access.require("eas")
    return {"items": eas_store.courses(), **eas_store.info()}


@router.post("/clear", summary="清空已保存的课表")
def clear():
    access.require("eas")
    eas_store.clear()
    return {"ok": True}


@router.get("/export", summary="导出教务课表日历（.ics）")
def export():
    access.require("eas")
    items = eas_store.courses()
    if not items:
        raise HTTPException(400, "还没有课表，先导入")
    start = term_store.term_start()
    if not start:
        raise HTTPException(400, "请先填学期第一周周一的日期")
    try:
        content = ics_mod.export(items, start)
    except ValueError as e:
        raise HTTPException(400, str(e)) from e
    name = f"eas-schedule-{time.strftime('%Y%m%d')}.ics"
    return Response(
        content="\ufeff" + content,
        media_type="text/calendar; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{name}"'},
    )
