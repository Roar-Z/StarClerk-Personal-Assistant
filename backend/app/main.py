"""FastAPI 应用入口：业务分组 + 生命周期 + 全局异常兜底 + 仅本机访问。"""
from __future__ import annotations

import asyncio
import json
import logging
import time
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles

from . import access, fault, license
from .api import routers
from .config import APP_VERSION, settings
from .db.sqlite import init_db
from .log import setup as setup_log
from .notify import notifier
from .tasks.reminder import reminder
from .tasks.scheduler import runner
from .tasks.study_sync import study_sync

setup_log()
log = logging.getLogger("main")


@asynccontextmanager
async def lifespan(_: FastAPI):
    init_db()
    notifier.bind_loop(asyncio.get_running_loop())
    # 巡检跑在独立子线程里，不占事件循环；关闭时 join，避免半截任务
    if settings.scheduler_enabled:
        runner.start()
    reminder.start()
    study_sync.start()
    info = license.info()
    log.info(
        "StarClerk 就绪：http://%s:%s（%s，并发上限 %s）",
        settings.app_host,
        settings.app_port,
        info["label"],
        info["max_concurrency"],
    )
    yield
    study_sync.stop()
    reminder.stop()
    runner.stop()
    log.info("StarClerk 已停止")


app = FastAPI(title="StarClerk", version=APP_VERSION, lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origin_regex=r"http://(127\.0\.0\.1|localhost)(:\d+)?",
    allow_methods=["*"],
    allow_headers=["*"],
)

# 三档权限：按路径查表，越权在进路由之前就被挡回去
app.middleware("http")(access.guard)

for r in routers:
    app.include_router(r, prefix="/api")

# 只服务本机（打包后窗口/托盘都是 127.0.0.1）
_LOOPBACK = {"127.0.0.1", "::1", "localhost"}


@app.middleware("http")
async def guard_local(request: Request, call_next):
    host = (request.client.host if request.client else "") or ""
    if host.replace("::ffff:", "") not in _LOOPBACK:
        return JSONResponse({"detail": "仅允许本机访问"}, status_code=403)
    started = time.perf_counter()
    response = await call_next(request)
    cost = (time.perf_counter() - started) * 1000
    if cost > 5000 and request.url.path != "/api/events":
        log.warning("慢请求 %s %s %.0fms", request.method, request.url.path, cost)
    return response


@app.exception_handler(Exception)
async def unhandled(request: Request, exc: Exception):
    """兜底：没被接口接住的异常也走 fault，日志、errors 表、弹窗一次到位。"""
    msg = fault.report("api", exc, title="服务异常")
    return JSONResponse(
        {"detail": f"{msg}（{request.method} {request.url.path}）"},
        status_code=500,
    )


@app.get("/api/events")
async def events():
    """SSE：巡检提醒/结果实时推到前端。"""
    q = notifier.subscribe()

    async def gen():
        try:
            while True:
                ev = await q.get()
                yield f"data: {json.dumps(ev, ensure_ascii=False)}\n\n"
        finally:
            notifier.unsubscribe(q)

    return StreamingResponse(gen(), media_type="text/event-stream", headers={"Cache-Control": "no-cache"})


@app.get("/api/health")
def health():
    info = license.info()
    return {
        "ok": True,
        "version": app.version,
        "scheduler": runner.alive,
        "plan": info["tier"],
        "perf_mode": info["perf_mode"],
    }


# ---- 前端静态资源：build 完的 dist 由同一进程托管，打包后不需要再跑 5173 ----
_DIST = settings.static_path
app.mount("/assets", StaticFiles(directory=_DIST / "assets", check_dir=False), name="assets")


@app.get("/{path:path}", include_in_schema=False)
def spa(path: str):
    if path.startswith("api/"):
        return JSONResponse({"detail": "接口不存在"}, status_code=404)
    index = _DIST / "index.html"
    if not index.is_file():
        return JSONResponse({"detail": "前端未构建，先在 frontend 下执行 npm run build"}, status_code=503)
    target = (_DIST / path).resolve()
    # 只允许 dist 目录内的文件，挡掉 ../ 之类的路径
    if path and target.is_file() and _DIST.resolve() in target.parents:
        return FileResponse(target)
    return FileResponse(index)
