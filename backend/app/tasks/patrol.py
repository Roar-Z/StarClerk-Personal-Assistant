"""巡检执行器：把 tasks 表的一行转成 Agent 输入，回结论 + 提醒信号。

真正的推理在 agent/graph.run_patrol，这里只做「数据库字段 → Agent 入参」的适配，
方便调度器、手动执行接口共用同一入口。
"""
from __future__ import annotations

from typing import Any

from ..agent import graph


def execute(task: dict[str, Any]) -> dict[str, Any]:
    return graph.run_patrol(
        task.get("name") or "巡检",
        task.get("prompt") or "",
        task.get("doc_scope") or "",
    )
