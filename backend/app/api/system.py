"""system 分组：版本信息、日志、开机自启、清理工具。

基本是本机维护操作，不带业务数据，所以未登录也能看；
真正动数据的清理（会话/向量库）还是按档位走 require()。
"""
from __future__ import annotations

import logging
import os
import platform
import subprocess
import sys
import threading
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


# ---------------------------------------------------------------- 卸载
def _uninstaller() -> Path | None:
    """卸载程序跟主程序放一个目录；源码跑就找 dist 里的那份。"""
    base = Path(sys.executable).parent if is_frozen() else Path(__file__).resolve().parents[3] / "dist"
    exe = base / "Uninstall.exe"
    return exe if exe.is_file() else None


def _exit_after(delay: float = 1.2) -> None:
    """给前端一点时间弹提示，再从进程层面退干净。"""
    def _run() -> None:
        from .. import launcher

        launcher.quit_app()

    threading.Timer(delay, _run).start()


@router.post("/uninstall", summary="调起卸载程序并退出")
def uninstall():
    """先把卸载器拉起来，自己再退，不然它一启动就检测到主程序占着端口。"""
    exe = _uninstaller()
    if exe is None:
        raise HTTPException(404, "没找到 Uninstall.exe，这版是绿色版，删目录就等于卸载")
    subprocess.Popen([str(exe)], cwd=str(exe.parent), close_fds=True)
    log.info("已打开卸载程序：%s", exe)
    _exit_after(0.8)
    return {"ok": True, "path": str(exe)}


# ---------------------------------------------------------------- 帮助 / 引导 / 更新
_HELP = """## 开始用

1. 到「模型」页点「登录」，未登录只能用 Kilo 的免费模型，登录后所有功能都开着。
2. 回到「对话」，第一句话随便问，先确认能通；想用自己的 key 再回「模型」页换。
3. 想让它认你的资料，去「资料」页传文档；登录后最多 500 份。

## 常用操作

- **导出对话**：对话页右上角，Markdown / 纯文本 / Word 三种。
- **让它定时盯着**：任务页新建，写清要它判断什么；填了网址就按网页变化触发。
- **记住你的习惯**：记忆页能看到它记了什么，不对的单条删掉。
- **待办和日程**：待办页输一句话就能拆出时间，重复事件自动排下一次，能导 CSV 和日历。
- **快递小票**：扫描页本地识字，取件码一键复制；采购清单按地点并成一张。
- **悬浮指令**：Ctrl + Alt + Space 弹命令面板；设置里能换主题、开悬浮窗。
- **换电脑**：系统页有迁移向导，导出 zip 带走。

## 数据在哪

全在安装目录的 `data` 下。`starcLerk.db` 是数据库，`uploads` 是传的文档，
`lancedb` 是向量索引。想彻底清掉就用系统页的清理工具。

## 卡住了

- 模型报 401：key 不对或过期。
- 模型报 429：上游限流，等一会儿或者换个模型。
- 检索没结果：文档切片没建好，把文档删了重传一次。
"""

_GUIDE = [
    {"key": "model", "title": "先登录", "body": "去「模型」页点一下「登录」，本机登录不联网，之后想用自己的 key 再在同一页换。", "page": "settings"},
    {"key": "chat", "title": "问第一句", "body": "直接打字问，Enter 发送。回答下面能看到用到的资料。", "page": "chat"},
    {"key": "todo", "title": "记件待办", "body": "「待办」页输一句话，比如「明早九点取快递」，它会自动拆好时间。", "page": "todo"},
    {"key": "rag", "title": "传份资料", "body": "「资料」页拖文件进去，建好索引后对话会自动检索。", "page": "knowledge"},
    {"key": "task", "title": "挂个任务", "body": "想让它在后台盯事情，去「任务」页新建，填网址就按页面变化提醒。", "page": "tasks"},
    {"key": "tier", "title": "看看能用多少", "body": "「模型」页能看到当前是未登录还是已登录，以及任务、资料、笔记的额度。", "page": "settings"},
]


@router.get("/help", summary="内置帮助文档")
def help_doc():
    return {"title": f"{APP_NAME} 使用说明", "version": APP_VERSION, "markdown": _HELP}


@router.get("/guide", summary="新手引导清单")
def guide():
    return {"items": _GUIDE, "done": bool(meta.kv_get("guide_done"))}


@router.post("/guide/done", summary="标记引导已看完")
def guide_done():
    meta.kv_set("guide_done", True)
    return {"ok": True}


def _ver(text: str) -> tuple[int, ...]:
    try:
        return tuple(int(x) for x in text.split("."))
    except ValueError:
        return ()


@router.get("/update", summary="手动检查更新（看本地安装包）")
def check_update():
    """不联网。扫 exe 同目录的安装包，版本号比当前高就提示一下。"""
    import re

    folder = Path(sys.executable).parent if is_frozen() else Path(__file__).resolve().parents[3] / "dist"
    latest, target = APP_VERSION, None
    if folder.is_dir():
        for p in folder.glob("*.exe"):
            m = re.search(r"(\d+\.\d+\.\d+)", p.name)
            if not m:
                continue
            if _ver(m.group(1)) > _ver(latest):
                latest, target = m.group(1), p
    has_new = bool(target) and _ver(latest) > _ver(APP_VERSION)
    return {
        "current": APP_VERSION,
        "latest": latest,
        "has_new": has_new,
        "file": str(target) if target else "",
        "folder": str(folder),
        "checked_at": time.strftime("%Y-%m-%d %H:%M"),
    }


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
