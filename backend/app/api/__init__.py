"""接口层按业务分组，main.py 统一挂到 /api 前缀下。

    chat     /api/chat       对话 + 会话 + 导出
    task     /api/tasks      托管任务 + 额度 + 执行 + 巡检日志
    memory   /api/memory     长期记忆（分组/备份/画像）
    rag      /api/rag        知识库导入/检索/工作区
    mindmap  /api/mindmap    思维导图
    notes    /api/notes      笔记知识库
    skills   /api/skills     技能模板
    ocr      /api/ocr        本地识字 + 快递单/小票
    shopping /api/shopping   采购清单合并
    todos    /api/todos      待办与日程
    migrate  /api/migrate    数据迁移向导
    license  /api/license    本地授权 + 低配模式
    stats    /api/stats      用量与异常
    config   /api/config     模型/向量配置
    system   /api/system     版本、日志、开机自启、清理、帮助
"""
from __future__ import annotations

from . import (
    chat,
    config,
    license,
    memory,
    migrate,
    mindmap,
    notes,
    ocr,
    rag,
    shopping,
    skills,
    stats,
    todos,
    system,
    task,
)

routers = (
    chat.router,
    task.router,
    memory.router,
    rag.router,
    mindmap.router,
    notes.router,
    skills.router,
    ocr.router,
    shopping.router,
    todos.router,
    migrate.router,
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
    "migrate",
    "mindmap",
    "notes",
    "ocr",
    "rag",
    "routers",
    "shopping",
    "skills",
    "stats",
    "system",
    "task",
    "todos",
]
