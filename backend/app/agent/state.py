"""Agent State：单条主线的极简 ReAct 状态，不引入子图 / 多 Agent / Checkpoint。

字段分四组：输入 → 检索素材（记忆、工具观测）→ 过程（计划、轨迹）→ 结论（回答、提醒信号、token 用量）。
列表型字段用 Annotated + add 做累加，避免节点里手写拼接。
"""
from __future__ import annotations

from operator import add
from typing import Annotated, Any, Literal, TypedDict

TaskMode = Literal["chat", "patrol"]
NotifyLevel = Literal["info", "warn"]


class ToolCall(TypedDict, total=False):
    """计划节点决定的一次工具调用（已把 arguments 解析成 dict）。"""

    id: str
    name: str
    arguments: dict[str, Any]


class Step(TypedDict, total=False):
    """思考/动作轨迹，只给前端展示和排查用，不回灌给模型。"""

    index: int
    kind: Literal["think", "tool", "finish"]
    content: str


class AgentState(TypedDict, total=False):
    # ---- 输入 ----
    query: str
    mode: TaskMode
    history: list[dict[str, str]]
    use_rag: bool
    allow_web: bool
    doc_scope: str
    max_steps: int
    persist_memory: bool

    # ---- 记忆召回（每轮思考前刷新）----
    memories: list[str]
    recalled_for: str

    # ---- 计划 ----
    iterations: int
    retries: int  # 因“信息不足”回退补检索的次数，最多 1 次
    pending_calls: list[ToolCall]
    draft: str
    need_more: bool
    steps: Annotated[list[Step], add]

    # ---- 工具观测 ----
    observations: Annotated[list[dict[str, Any]], add]
    contexts: list[dict[str, Any]]

    # ---- 结论 ----
    answer: str
    error: str
    should_notify: bool
    notify_level: NotifyLevel

    # ---- 成本 ----
    usage: dict[str, int]


def merge_usage(*items: dict[str, int] | None) -> dict[str, int]:
    """累加多轮调用的 token 用量。"""
    total = {"calls": 0, "prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}
    for it in items:
        for k in total:
            total[k] += int((it or {}).get(k, 0))
    return total
