"""接口层按业务分组，main.py 统一挂到 /api 前缀下。

    chat     /api/chat       对话 + 会话 + 导出
    task     /api/tasks      托管任务 + 额度 + 执行 + 巡检日志
    memory   /api/memory     长期记忆（分组/备份是 Pro）
    rag      /api/rag        知识库导入/检索/工作区
    mindmap  /api/mindmap    思维导图（Pro）
    license  /api/license    本地授权 + 低配模式
    stats    /api/stats      用量与异常
    config   /api/config     模型/向量配置
    system   /api/system     版本、日志、开机自启、清理
"""
from __future__ import annotations

from . import chat, config, license, memory, mindmap, rag, stats, system, task

routers = (
    chat.router,
    task.router,
    memory.router,
    rag.router,
    mindmap.router,
    license.router,
    stats.router,
    config.router,
    system.router,
)

__all__ = [
    "chat",
    "config",
    "license",
    "memory",
    "mindmap",
    "rag",
    "routers",
    "stats",
    "system",
    "task",
]
