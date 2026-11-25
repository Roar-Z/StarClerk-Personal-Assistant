"""巡检执行器：把 tasks 表的一行转成 Agent 输入，回结论 + 提醒信号。

带 url 的任务先抓一遍网页，跟上次的摘要比一下：没变就直接结束，省一次模型调用；
变了才把正文塞进 prompt 让模型判断。第一次跑只记基线，不提醒。
"""
from __future__ import annotations

import hashlib
import logging
import re
from typing import Any

import httpx

from ..agent import graph
from ..db import models as meta

log = logging.getLogger("patrol")

PAGE_LIMIT = 12000


def _fetch(url: str) -> str:
    """没引 HTML 解析库，正则去标签留文字，模型能读就行。"""
    with httpx.Client(
        timeout=20,
        follow_redirects=True,
        headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) StarClerk/1.0"},
    ) as c:
        r = c.get(url)
        r.raise_for_status()
        html = r.text

    html = re.sub(r"(?is)<(script|style|head|noscript).*?</\1>", " ", html)
    text = re.sub(r"(?s)<[^>]+>", " ", html)
    for old, new in (("&nbsp;", " "), ("&amp;", "&"), ("&lt;", "<"), ("&gt;", ">"), ("&quot;", '"')):
        text = text.replace(old, new)
    return re.sub(r"\s+", " ", text).strip()[:PAGE_LIMIT]


def execute(task: dict[str, Any]) -> dict[str, Any]:
    url = (task.get("url") or "").strip()
    name = task.get("name") or "巡检"

    if url:
        try:
            page = _fetch(url)
        except Exception as e:  # noqa: BLE001  网络问题要报，不能悄悄当成功
            log.warning("监控页抓取失败 %s：%s", url, e)
            return {
                "ok": False,
                "result": f"页面打不开：{str(e)[:150]}",
                "should_notify": True,
                "level": "warn",
                "notice": {"title": f"监控失败 · {name}", "body": f"{url}\n{str(e)[:120]}", "level": "warn"},
            }

        digest = hashlib.md5(page.encode("utf-8")).hexdigest()
        last = task.get("last_value") or ""
        meta.set_task_value(task["id"], digest)
        if not last:
            return {
                "ok": True,
                "result": f"已记录页面基线（{len(page)} 字），下一轮开始比对变化",
                "should_notify": False,
                "level": "info",
            }
        if digest == last:
            return {"ok": True, "result": f"页面没变化：{url}", "should_notify": False, "level": "info"}

        task = {
            **task,
            "prompt": f"{task.get('prompt') or ''}\n\n监控页面：{url}\n当前正文：{page[:8000]}",
        }

    return graph.run_patrol(
        name,
        task.get("prompt") or "",
        task.get("doc_scope") or "",
        task.get("workspace") or "",
    )
