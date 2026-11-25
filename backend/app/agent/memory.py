"""长期记忆：写入（LLM 抽取事实）+ 召回（向量 top-k）。

设计上是"轻量记忆"：只沉淀稳定的偏好/事实/待办，避免污染上下文。
"""
from __future__ import annotations

import logging
import re

from ..db import models as meta
from ..llm.client import chat
from ..vector import lancedb_store as vs

log = logging.getLogger("memory")

EXTRACT_PROMPT = """从下面这轮对话里抽取值得长期记住的信息（用户偏好、身份事实、长期待办、重要结论）。
要求：每条一行，以 "- " 开头，最多 3 条；没有值得记的就只输出 NONE。
不要复述整段对话，不要编造。"""


def extract_and_store(user_text: str, assistant_text: str) -> list[str]:
    if len(user_text.strip()) < 8 or not assistant_text.strip():
        return []  # 太短的寒暄不值得多花一次模型调用
    convo = f"用户：{user_text[:1500]}\n助手：{assistant_text[:1500]}"
    try:
        out = chat(
            [{"role": "system", "content": EXTRACT_PROMPT}, {"role": "user", "content": convo}],
            temperature=0,
            scope="memory",
        )
    except Exception as e:  # noqa: BLE001
        log.warning("记忆抽取失败：%s", e)
        return []
    if "NONE" in out.upper() and len(out) < 12:
        return []
    items = [re.sub(r"^[-*\d.\s]+", "", ln).strip() for ln in out.splitlines()]
    items = [i for i in items if 4 <= len(i) <= 200][:3]
    for it in items:
        _store(it)
    return items


def _store(text: str) -> None:
    existing = {m["content"] for m in meta.list_memories(500)}
    if text in existing:
        return
    m = meta.add_memory(text)
    try:
        vs.add_memory(m["id"], text)
    except Exception as e:  # noqa: BLE001
        log.warning("记忆向量写入失败：%s", e)


def recall(query: str, top_k: int = 4) -> list[str]:
    try:
        return [m["text"] for m in vs.search_memories(query, top_k)]
    except Exception as e:  # noqa: BLE001
        log.warning("记忆召回失败，退化为最近记忆：%s", e)
        return [m["content"] for m in meta.list_memories(top_k)]
