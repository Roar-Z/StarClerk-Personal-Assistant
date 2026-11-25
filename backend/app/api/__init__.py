"""接口层按业务分组，main.py 统一挂到 /api 前缀下。

    chat    /api/chat          对话 + 会话
    task    /api/tasks         托管任务 + 额度 + 手动执行
    memory  /api/memory        长期记忆
    rag     /api/rag           知识库导入/检索
    stats   /api/stats         用量与异常
    config  /api/config        模型/向量/套餐配置
"""
from __future__ import annotations

from . import chat, config, memory, rag, stats, task

routers = (chat.router, task.router, memory.router, rag.router, stats.router, config.router)

__all__ = ["chat", "config", "memory", "rag", "routers", "stats", "task"]
