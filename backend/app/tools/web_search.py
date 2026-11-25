"""网页搜索工具：有 Tavily Key 用 Tavily，否则退回 DuckDuckGo HTML（均无需额外依赖）。

只返回 {title, url, snippet}，不做正文抓取——MVP 阶段够用，也避免拖长延迟。
"""
from __future__ import annotations

import html
import re
from urllib.parse import parse_qs, unquote, urlparse

import httpx

from ..config import settings

TAVILY_URL = "https://api.tavily.com/search"
DDG_URL = "https://html.duckduckgo.com/html/"
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) StarClerk/0.1"


class ToolError(RuntimeError):
    """工具级失败：由 registry 捕获后作为观测回给模型，而不是中断整个图。"""


def run(query: str, top_k: int = 5) -> dict:
    q = (query or "").strip()
    if not q:
        raise ToolError("query 不能为空")
    if not settings.web_search_enabled:
        raise ToolError("网页搜索已关闭，可在设置中开启")
    k = max(1, min(int(top_k or 5), 8))
    items = _tavily(q, k) if settings.tavily_api_key else _duckduckgo(q, k)
    if not items:
        raise ToolError("没有搜索到结果（网络受限或关键词过窄）")
    return {"items": items[:k]}


def _tavily(q: str, k: int) -> list[dict]:
    payload = {"api_key": settings.tavily_api_key, "query": q, "max_results": k, "search_depth": "basic"}
    with httpx.Client(timeout=settings.web_search_timeout) as c:
        r = c.post(TAVILY_URL, json=payload)
    if r.status_code >= 400:
        raise ToolError(f"Tavily {r.status_code}: {r.text[:120]}")
    return [
        {"title": x.get("title", ""), "url": x.get("url", ""), "snippet": (x.get("content") or "")[:400]}
        for x in r.json().get("results", [])
    ]


def _duckduckgo(q: str, k: int) -> list[dict]:
    with httpx.Client(timeout=settings.web_search_timeout, headers={"User-Agent": UA}) as c:
        r = c.post(DDG_URL, data={"q": q, "kl": "cn-zh"})
    if r.status_code >= 400:
        raise ToolError(f"DuckDuckGo {r.status_code}")
    body = r.text
    links = re.findall(r'class="result__a"[^>]*href="([^"]+)"[^>]*>(.*?)</a>', body, re.S)
    snippets = re.findall(r'class="result__snippet"[^>]*>(.*?)</a>', body, re.S)
    out: list[dict] = []
    for i, (href, title) in enumerate(links[:k]):
        out.append(
            {
                "title": _clean(title),
                "url": _real_url(href),
                "snippet": _clean(snippets[i]) if i < len(snippets) else "",
            }
        )
    return out


def _clean(raw: str) -> str:
    return html.unescape(re.sub(r"<[^>]+>", "", raw)).strip()


def _real_url(href: str) -> str:
    """DDG 结果链接是跳转形式 //duckduckgo.com/l/?uddg=<url>，还原成真实地址。"""
    if "uddg=" in href:
        values = parse_qs(urlparse(href).query).get("uddg")
        if values:
            return unquote(values[0])
    return href if href.startswith("http") else f"https:{href}"
