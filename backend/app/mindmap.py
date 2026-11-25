"""长文档思维导图（Pro）：把一篇资料压成 markdown 大纲。

步骤很朴素：拿正文 → 截断 → 让模型按「一个标题 + 缩进列表」输出 → 规整格式。
规整这一步别省，小模型经常多嘴写解释、圆点左右混用，直接丢给前端就花了。
生成结果顺手存一份 md 到 data/mindmaps，导出就是把这个文件发回去。
"""
from __future__ import annotations

import logging
import re
import time
import uuid
from typing import Any

from .config import settings
from .llm import client
from .vector import lancedb_store as vs

log = logging.getLogger("mindmap")

MAX_CHARS = 12000
_DIR = "mindmaps"

_PROMPT = """你是整理笔记的助手。请把下面材料提炼成层级清晰的思维导图。

要求：
1. 第一行是主题，格式 "# 主题"
2. 子节点用 "- " 开头，层级靠两个空格缩进
3. 只保留 3~4 层，节点不超过 25 个，每条不超过 20 字
4. 不要输出解释、不要代码块，直接给我大纲

材料：
{content}"""


def _dir():
    p = settings.data_path / _DIR
    p.mkdir(parents=True, exist_ok=True)
    return p


def _bullets(line: str) -> str:
    """把各种乱七八糟的列表符号统一成 - """
    return re.sub(r"^\s*([*+•·●○▪]|\d+[.)、])\s*", "- ", line)


def _tidy(raw: str, fallback_title: str) -> str:
    """清掉代码块和废话，保证输出能被前端当 markdown 用。"""
    text = (raw or "").replace("```markdown", "").replace("```", "").strip()
    lines: list[str] = []
    root = ""
    for line in text.splitlines():
        s = line.rstrip()
        if not s.strip():
            continue
        if s.lstrip().startswith("#"):
            if not root:
                root = s.lstrip("# ").strip() or fallback_title
                lines.append(f"# {root}")
            # 低层级标题当普通节点处理，避免出现两个根
            continue
        if not s.lstrip().startswith(("-", "*", "+")) and not re.match(r"^\s*\d+[.)、]", s):
            # 不是列表的句子：短句当节点，长句可能是模型在解释，丢掉
            if len(s) <= 40 and lines:
                indent = len(s) - len(s.lstrip())
                lines.append(" " * min(indent, 6) + "- " + s.strip())
            continue
        indent = len(s) - len(s.lstrip())
        lines.append(" " * min(indent, 6) + _bullets(s.strip()))
    if not root:
        lines.insert(0, f"# {fallback_title}")
    # 只留 30 行，太长的导图看着累
    return "\n".join(lines[:30])


def generate(text: str = "", doc_id: str = "", title: str = "") -> dict[str, Any]:
    """text 和 doc_id 二选一；doc_id 会从向量库把正文拼回来。"""
    content = (text or "").strip()
    name = (title or "").strip()
    if not content and doc_id:
        content = vs.document_text(doc_id, MAX_CHARS)
        if not name:
            for d in vs.list_documents():
                if d["doc_id"] == doc_id:
                    name = str(d["source"])
                    break
    if len(content) < 20:
        raise ValueError("内容太少了，至少给一段话或者选一份有内容的文档")
    name = name or "思维导图"

    started = time.perf_counter()
    res = client.complete(
        [
            {"role": "system", "content": "你只输出 markdown 大纲，不闲聊。"},
            {"role": "user", "content": _PROMPT.format(content=content[:MAX_CHARS])},
        ],
        temperature=0.3,
        scope="mindmap",
    )
    markdown = _tidy(res.content, name)
    mid = uuid.uuid4().hex[:12]
    file = _dir() / f"{mid}.md"
    file.write_text(markdown + "\n", encoding="utf-8")
    nodes = sum(1 for line in markdown.splitlines() if line.strip().startswith("-"))
    log.info("思维导图生成完成：%s，%d 个节点，%.1fs", name, nodes, time.perf_counter() - started)
    return {
        "id": mid,
        "title": name,
        "markdown": markdown,
        "nodes": nodes,
        "provider": res.provider,
        "model": res.model,
        "elapsed_ms": res.latency_ms,
    }


def path_of(mid: str) -> Any:
    """只允许取自己生成的文件，防止 ../ 穿越。"""
    if not re.fullmatch(r"[0-9a-f]{12}", mid or ""):
        return None
    p = _dir() / f"{mid}.md"
    return p if p.is_file() else None


def recent(limit: int = 10) -> list[dict[str, Any]]:
    files = sorted(_dir().glob("*.md"), key=lambda p: p.stat().st_mtime, reverse=True)[:limit]
    out = []
    for p in files:
        try:
            head = p.read_text(encoding="utf-8").splitlines()[0].lstrip("# ").strip()
        except (OSError, IndexError):
            head = p.stem
        out.append({"id": p.stem, "title": head, "size": p.stat().st_size})
    return out
