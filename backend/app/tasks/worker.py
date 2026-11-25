"""单次巡检的执行壳：调 Agent、落结果、写历史日志、决定要不要提醒。

调度队列和「立即执行」接口都走这里，保证两条路径的行为一致。
"""
from __future__ import annotations

import logging
import time
from typing import Any

from ..db import models as meta
from ..notify.notifier import notify
from .patrol import execute

log = logging.getLogger("patrol")

LOG_KEEP = 2000


def run_task(task: dict[str, Any], notify_user: bool = True) -> dict[str, Any]:
    """执行一次巡检：异常收敛成结果，提醒标记交给托盘/SSE。

    notify_user=False 用于「用户手动点执行」——结果已在界面上显示，不再弹托盘。
    """
    name = task.get("name") or "巡检"
    started = time.perf_counter()
    try:
        res = execute(task)
    except Exception as e:  # noqa: BLE001
        log.exception("任务 %s 执行失败", name)
        meta.add_error("patrol", f"{name}: {type(e).__name__}: {e}")
        res = {
            "ok": False,
            "result": f"巡检失败：{str(e)[:200]}",
            "should_notify": True,
            "level": "warn",
            "notice": {"title": f"巡检失败 · {name}", "body": str(e)[:180], "level": "warn"},
        }

    elapsed = int((time.perf_counter() - started) * 1000)
    ok = bool(res.get("ok", True))
    result_text = str(res.get("result") or "")
    meta.finish_task(task["id"], result_text)
    _write_log(task, ok, str(res.get("level") or "info"), result_text, elapsed)

    if notify_user:
        if not ok:
            # 巡检本身失败（模型/向量不可用）也要告诉用户，否则“静默成功”更糟
            notify(f"巡检失败 · {name}", result_text[:180] or "未知错误", "warn")
        elif res.get("should_notify") and res.get("notice"):
            notice = res["notice"]
            notify(notice["title"], notice["body"], notice.get("level", "info"))
    log.info("任务 %s 本轮结束：%.1fs，提醒=%s", name, time.perf_counter() - started, bool(res.get("should_notify")))
    return res


def _write_log(task: dict[str, Any], ok: bool, level: str, text: str, elapsed: int) -> None:
    try:
        meta.add_task_log(task["id"], task.get("name") or "巡检", ok, level, text, elapsed)
        if meta.count_task_logs() > LOG_KEEP:
            meta.prune_task_logs(LOG_KEEP)
    except Exception as e:  # noqa: BLE001  日志写失败不影响巡检结果
        log.warning("巡检日志入库失败：%s", e)
