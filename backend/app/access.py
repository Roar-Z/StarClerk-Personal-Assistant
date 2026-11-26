"""两档权限：一张功能表 + 一张路由表，中间件照着表拦。

思路很简单：先把每个接口归到一个"功能"上，再给功能定最低档位。
中间件在进路由之前查表，越权直接 403，接口里就不用到处写 if 了；
只有少数顺手要判断的地方（比如导出、额度）才调 require()。
"""
from __future__ import annotations

from fastapi import HTTPException, Request
from fastapi.responses import JSONResponse

from . import license

# 功能 → 最低档位
FEATURES: dict[str, str] = {
    "chat": "guest",  # 对话、临时会话消息
    "model": "guest",  # 读模型配置，未登录也能看（但只能看免费模型那条）
    "model_write": "free",  # 改模型 / 测试连接 / 重建索引要登录后才能用
    "session": "free",  # 会话列表 / 新建 / 删除
    "export": "free",  # 导出 Markdown
    "tasks": "free",  # 托管巡检
    "memory": "free",  # 基础长期记忆
    "rag": "free",  # 轻量知识库
    "usage": "free",  # token 用量
    "mindmap": "free",  # 长文档思维导图
    "workspace": "free",  # 多知识库工作区
    "extract": "free",  # 票据抽取
    "batch": "free",  # 文档批量导入导出
    "batch_ai": "free",  # 批量摘要 / 翻译 / 表格
    "memory_group": "free",  # 记忆分组 / 归档
    "memory_backup": "free",  # 记忆备份导入导出
    "profile": "free",  # 画像与智能整理
    "note": "free",  # 笔记知识库
    "skill_view": "free",  # 内置模板只读
    "skill_write": "free",  # 新建/编辑/导入导出
    "log_export": "free",  # 巡检日志导出
    "migrate": "free",  # 数据迁移
    "usage_detail": "free",  # 按会话/任务拆用量、告警
    "ocr": "guest",  # 本地 OCR 不花模型钱，未登录也能用
    "shopping": "free",  # 采购清单合并
    "todo": "free",  # 待办与日程
    "study": "free",  # 学习空间：学习通扫码作业提醒
    "focus": "free",  # 专注番茄钟
    "eas": "free",  # 教务课表导入
}

# (方法, 路径前缀, 功能)；从上往下匹配，命中第一条就停
# "*" 表示不限方法；更具体的路径要写在前面
RULES: tuple[tuple[str, str, str], ...] = (
    ("*", "/api/license", "chat"),
    ("*", "/api/health", "chat"),
    ("*", "/api/events", "chat"),
    ("GET", "/api/chat/export", "export"),
    ("*", "/api/stats/usage/detail", "usage_detail"),
    ("GET", "/api/chat/sessions/", "chat"),  # 单个会话的消息，未登录也能读内存里的
    ("*", "/api/chat/sessions", "session"),
    ("*", "/api/chat", "chat"),
    ("*", "/api/ocr", "ocr"),
    ("*", "/api/shopping", "shopping"),
    ("*", "/api/todos", "todo"),
    ("*", "/api/study", "study"),
    ("*", "/api/focus", "focus"),
    ("*", "/api/eas", "eas"),
    ("*", "/api/mindmap", "mindmap"),
    ("GET", "/api/tasks/logs/export", "log_export"),
    ("*", "/api/tasks/logs", "tasks"),
    ("*", "/api/tasks", "tasks"),
    ("*", "/api/memory/backup", "memory_backup"),
    ("*", "/api/memory/groups", "memory_group"),
    ("*", "/api/memory/profile", "profile"),
    ("*", "/api/memory/organize", "profile"),
    ("*", "/api/memory/summarize", "profile"),
    ("*", "/api/memory", "memory"),
    ("*", "/api/notes", "note"),
    ("GET", "/api/skills", "skill_view"),
    ("*", "/api/skills", "skill_write"),
    ("*", "/api/migrate", "migrate"),
    ("*", "/api/rag/workspaces", "workspace"),
    ("*", "/api/rag/extract", "extract"),
    ("*", "/api/rag/batch-ai", "batch_ai"),
    ("*", "/api/rag/batch", "batch"),
    ("*", "/api/rag", "rag"),
    ("*", "/api/stats", "usage"),
    # 写配置的三个口子单独拎出来，未登录只能 GET 看看当前用的是哪个模型
    ("POST", "/api/config/test", "model_write"),
    ("POST", "/api/config/rebuild-vector", "model_write"),
    ("PUT", "/api/config", "model_write"),
    ("*", "/api/config", "model"),
    ("*", "/api/system", "model"),  # 版本/日志/自启属于本机维护，未登录也能看
)

# 各档位的数量上限，超出就 409，别让一个免费用户塞满向量库
LIMITS: dict[str, dict[str, int]] = {
    "guest": {"tasks": 0, "docs": 0, "memories": 0, "notes": 0, "todos": 0},
    "free": {"tasks": 5, "docs": 500, "memories": 2000, "notes": 500, "todos": 500},
}


def limits_for(tier: str | None = None) -> dict[str, int]:
    return dict(LIMITS.get(tier or license.tier(), LIMITS["guest"]))


def allowed(feature: str, tier: str | None = None) -> bool:
    need = FEATURES.get(feature, "free")
    now = tier or license.tier()
    return license.RANK.get(now, 0) >= license.RANK.get(need, 1)


def feature_of(method: str, path: str) -> str | None:
    for rule_method, prefix, feature in RULES:
        if rule_method != "*" and rule_method != method:
            continue
        if path == prefix:
            return feature
        # 前缀带斜杠的规则（如 /api/chat/sessions/）只匹配子路径
        if prefix.endswith("/") and path.startswith(prefix):
            return feature
        if not prefix.endswith("/") and path.startswith(prefix + "/"):
            return feature
    return None


def require(feature: str) -> None:
    """接口内部再确认一次，主要给额度相关的分支用。"""
    if allowed(feature):
        return
    raise HTTPException(403, "未登录用不了这个功能，到「模型」页登录")


def check_limit(kind: str, used: int) -> None:
    """数量类限制：任务数、文档数、记忆条数共用一个出口。"""
    limit = limits_for().get(kind, 0)
    if used >= limit:
        raise HTTPException(409, f"{kind}最多 {limit} 个，删掉旧的再试")


async def guard(request: Request, call_next):
    """统一拦截：先查表，再放行，接口本身不用重复判断。"""
    path = request.url.path
    if path.startswith("/api/"):
        feature = feature_of(request.method, path)
        if feature and not allowed(feature):
            need = FEATURES.get(feature, "free")
            return JSONResponse(
                {
                    "detail": "未登录用不了这个功能，到「模型」页登录",
                    "feature": feature,
                    "need": need,
                    "tier": license.tier(),
                },
                status_code=403,
            )
    return await call_next(request)
