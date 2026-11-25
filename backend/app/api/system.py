"""system 分组：版本信息、日志、开机自启、清理工具。

基本是本机维护操作，不带业务数据，所以游客也能看；
真正动数据的清理（会话/向量库）还是按档位走 require()。
"""
from __future__ import annotations

import logging
import os
import platform
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Literal

from fastapi import APIRouter, HTTPException, Response
from pydantic import BaseModel

from .. import access, license
from ..config import APP_NAME, APP_VERSION, is_frozen, settings
from ..db import models as meta
from ..db import sqlite as db
from ..desktop import autostart
from ..log import export_bytes, files, prune
from ..vector import lancedb_store as vs

router = APIRouter(prefix="/system", tags=["system"])
log = logging.getLogger("system")

_BOOT = time.time()
_CLEAN_LABEL = {"sessions": "会话记录", "vector": "向量库", "config": "模型配置"}


def _built_at() -> str:
    """装好的版本看 exe 的修改时间，源码跑就空着。"""
    if not is_frozen():
        return ""
    try:
        return datetime.fromtimestamp(Path(sys.executable).stat().st_mtime).strftime("%Y-%m-%d %H:%M")
    except OSError:
        return ""


@router.get("/info", summary="版本与运行环境")
def info():
    lic = license.info()
    return {
        "name": APP_NAME,
        "version": APP_VERSION,
        "build": "安装版" if is_frozen() else "源码",
        "built_at": _built_at(),
        "python": platform.python_version(),
        "system": f"{platform.system()} {platform.release()}",
        "exe": sys.executable,
        "port": settings.app_port,
        "data_dir": str(settings.data_path),
        "log_dir": str(settings.log_path),
        "uptime": int(time.time() - _BOOT),
        "tier": lic["tier"],
        "tier_label": lic["label"],
        "perf_mode": lic["perf_mode"],
        "max_concurrency": lic["max_concurrency"],
        "counts": {
            "sessions": len(meta.list_sessions(999)),
            "tasks": len(meta.list_tasks()),
            "memories": meta.count_memories(),
            **vs.stats(),
        },
    }


# ---------------------------------------------------------------- 日志
@router.get("/logs", summary="日志文件列表")
def log_list():
    items = files()
    return {"dir": str(settings.log_path), "items": items, "total": sum(i["size"] for i in items)}


@router.get("/logs/export", summary="导出日志（zip）")
def log_export():
    data = export_bytes()
    if not data:
        raise HTTPException(404, "还没有日志可以导出")
    stamp = time.strftime("%Y%m%d-%H%M")
    return Response(
        data,
        media_type="application/zip",
        headers={"Content-Disposition": f'attachment; filename="starcLerk-logs-{stamp}.zip"'},
    )


@router.delete("/logs", summary="清理过期日志")
def log_prune():
    return {"ok": True, "removed": prune()}


class RevealIn(BaseModel):
    target: Literal["logs", "data"] = "logs"


@router.post("/reveal", summary="在资源管理器里打开目录")
def reveal(body: RevealIn):
    path = settings.log_path if body.target == "logs" else settings.data_path
    try:
        os.startfile(str(path))  # noqa: S606
    except Exception as e:  # noqa: BLE001
        raise HTTPException(500, f"打不开目录：{e}") from e
    return {"ok": True, "path": str(path)}


# ---------------------------------------------------------------- 开机自启
class AutoIn(BaseModel):
    on: bool


@router.get("/autostart", summary="开机自启状态")
def autostart_get():
    return autostart.status()


@router.put("/autostart", summary="开关开机自启")
def autostart_set(body: AutoIn):
    state = autostart.set_enabled(body.on)
    if state["supported"] and state["enabled"] != body.on:
        raise HTTPException(500, "注册表写入失败，可能被安全软件拦了")
    return state


# ---------------------------------------------------------------- 清理
class CleanIn(BaseModel):
    what: Literal["sessions", "vector", "config", "all"]


def _reset_config() -> None:
    """回到出厂设置：删 .env 和 kv 缓存，授权留着。"""
    env = settings.env_path
    if env.is_file():
        try:
            env.unlink()
        except OSError as e:
            raise HTTPException(500, f"删不掉 .env：{e}") from e
    db.exec_sql("DELETE FROM kv")


@router.post("/clean", summary="一键清理：会话 / 向量库 / 配置")
def clean(body: CleanIn):
    targets = ["sessions", "vector", "config"] if body.what == "all" else [body.what]
    done: list[str] = []
    for t in targets:
        if t == "sessions":
            access.require("session")
            db.exec_sql("DELETE FROM messages")
            db.exec_sql("DELETE FROM sessions")
        elif t == "vector":
            access.require("rag")
            vs.reset()
        else:
            _reset_config()
        done.append(_CLEAN_LABEL[t])
    log.info("已清理：%s", "、".join(done))
    return {"ok": True, "done": done, "need_restart": "config" in targets}
