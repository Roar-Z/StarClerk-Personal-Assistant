"""统一 LLM 适配器：所有厂商都走 OpenAI 兼容协议（/chat/completions、/embeddings）。

- 云端：豆包 Ark、Kimi(Moonshot)、通义 DashScope 兼容模式、DeepSeek
- 本地：Ollama（http://127.0.0.1:11434/v1）
- 云端异常自动降级到 Ollama，保证离线可用
- 内置 tool calling 与 token 统计（进程内累计，重启归零）

complete() 是唯一底层入口；chat() 是只取文本的薄封装，供不需要工具/用量的调用方使用。
"""
from __future__ import annotations

import copy
import json
import logging
import threading
import time
from contextlib import contextmanager
from dataclasses import dataclass, field
from typing import Any, Iterator

import httpx

from ..config import settings
from ..license import MAX_CONCURRENCY

log = logging.getLogger("llm")

PROVIDERS: dict[str, dict[str, Any]] = {
    "doubao": {
        "label": "豆包 Ark",
        "base_url": "https://ark.cn-beijing.volces.com/api/v3",
        "model": "doubao-seed-1-6-250615",
    },
    "kimi": {"label": "Kimi", "base_url": "https://api.moonshot.cn/v1", "model": "moonshot-v1-8k"},
    "qwen": {
        "label": "通义千问",
        "base_url": "https://dashscope.aliyuncs.com/compatible-mode/v1",
        "model": "qwen-plus",
    },
    "deepseek": {"label": "DeepSeek", "base_url": "https://api.deepseek.com/v1", "model": "deepseek-chat"},
    "ollama": {
        "label": "Ollama 本地",
        "base_url": "http://127.0.0.1:11434/v1",
        "model": "qwen2.5:7b",
        "api_key": "ollama",
    },
    "custom": {"label": "自定义", "base_url": "", "model": ""},
}

# 统计只记对话用量；embedding 的 token 各厂商口径不一，MVP 不混统计
_LOCK = threading.Lock()
_STATS: dict[str, Any] = {
    "calls": 0,
    "prompt_tokens": 0,
    "completion_tokens": 0,
    "total_tokens": 0,
    "by_model": {},
}


class LLMError(RuntimeError):
    pass


# ---------------------------------------------------------------- 并发闸门
# 本地机器同时打两路模型就到顶了，多出来的排队等，别把内存和显存一起打满
_sem = threading.BoundedSemaphore(MAX_CONCURRENCY)
_gate_lock = threading.Lock()
_busy = 0
_waiting = 0


@contextmanager
def gate() -> Iterator[None]:
    global _busy, _waiting
    with _gate_lock:
        _waiting += 1
    _sem.acquire()
    with _gate_lock:
        _waiting -= 1
        _busy += 1
    try:
        yield
    finally:
        with _gate_lock:
            _busy -= 1
        _sem.release()


def gate_stats() -> dict[str, int]:
    with _gate_lock:
        return {"limit": MAX_CONCURRENCY, "busy": _busy, "waiting": _waiting}


@dataclass(slots=True)
class LLMResult:
    content: str
    tool_calls: list[dict[str, Any]] = field(default_factory=list)
    usage: dict[str, int] = field(default_factory=dict)
    provider: str = ""
    model: str = ""
    latency_ms: int = 0
    fallback: bool = False


# ---------------------------------------------------------------- 配置解析
def _conf(provider: str | None) -> tuple[str, str, str, str]:
    """返回 (base_url, model, api_key, provider_name)。

    当前服务商直接用设置页里的值（用户可能填了自建网关/中转）；
    显式指定其它服务商时用预设，避免串用错误地址。
    """
    name = (provider or settings.llm_provider or "custom").lower()
    preset = PROVIDERS.get(name, PROVIDERS["custom"])
    if name == (settings.llm_provider or "").lower() and settings.llm_base_url:
        return (
            settings.llm_base_url,
            settings.llm_model or preset["model"],
            settings.llm_api_key or preset.get("api_key", ""),
            name,
        )
    return preset.get("base_url", ""), preset.get("model", ""), preset.get("api_key", ""), name


def _fallback_ready() -> bool:
    return settings.fallback_enabled and settings.llm_base_url.rstrip("/") != settings.fallback_base_url.rstrip("/")


# ---------------------------------------------------------------- HTTP
def _post(base_url: str, api_key: str, path: str, payload: dict[str, Any], timeout: float) -> dict:
    if not base_url:
        raise LLMError("模型地址为空，请先在设置里选择服务商")
    url = base_url.rstrip("/") + path
    headers = {"Content-Type": "application/json"}
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"
    try:
        with httpx.Client(timeout=timeout) as c:
            r = c.post(url, json=payload, headers=headers)
    except httpx.HTTPError as e:
        raise LLMError(f"网络错误：{e}") from e
    if r.status_code >= 400:
        raise LLMError(f"{r.status_code} {r.text[:300]}")
    return r.json()


def _tool_unsupported(err: LLMError) -> bool:
    text = str(err).lower()
    return "tool" in text and ("400" in text or "not support" in text or "invalid" in text)


# ---------------------------------------------------------------- 用量统计
def _usage(raw: dict | None) -> dict[str, int]:
    raw = raw or {}
    prompt = int(raw.get("prompt_tokens") or 0)
    completion = int(raw.get("completion_tokens") or 0)
    return {
        "calls": 1,
        "prompt_tokens": prompt,
        "completion_tokens": completion,
        "total_tokens": int(raw.get("total_tokens") or prompt + completion),
    }


def _record(provider: str, model: str, usage: dict[str, int], scope: str, latency_ms: int) -> None:
    with _LOCK:
        for k in ("calls", "prompt_tokens", "completion_tokens", "total_tokens"):
            _STATS[k] += usage.get(k, 0)
        bucket = _STATS["by_model"].setdefault(
            f"{provider}:{model}", {"calls": 0, "prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}
        )
        for k in bucket:
            bucket[k] += usage.get(k, 0)
    # 落库：按天/按场景统计，重启不清零；失败不影响主流程
    try:
        from ..db import models as meta

        meta.add_usage(scope, provider, model, usage, latency_ms)
    except Exception as e:  # noqa: BLE001
        log.debug("用量入库失败：%s", e)


def stats() -> dict[str, Any]:
    """当前进程累计的 token 用量（设置页/排查用）。"""
    with _LOCK:
        return copy.deepcopy(_STATS)


def reset_stats() -> None:
    with _LOCK:
        _STATS.update({"calls": 0, "prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0, "by_model": {}})


# ---------------------------------------------------------------- 主入口
def complete(
    messages: list[dict[str, Any]],
    tools: list[dict] | None = None,
    temperature: float | None = None,
    model: str | None = None,
    provider: str | None = None,
    scope: str = "chat",
) -> LLMResult:
    """scope 用于 token 统计分桶：chat / patrol / memory / probe。"""
    base_url, mdl, api_key, name = _conf(provider)
    payload: dict[str, Any] = {
        "model": model or mdl,
        "messages": messages,
        "temperature": settings.llm_temperature if temperature is None else temperature,
        "stream": False,
    }
    if tools:
        payload["tools"] = tools
        payload["tool_choice"] = "auto"

    started = time.perf_counter()
    fallback = False
    # 排队拿槽位；模型慢的时候这里会等一会儿，但不额外占线程
    with gate():
        try:
            data = _post(base_url, api_key, "/chat/completions", payload, settings.llm_timeout)
        except LLMError as e:
            if tools and _tool_unsupported(e):
                # 少数兼容实现不支持工具字段：去掉后重试一次，由计划节点按纯文本处理
                log.warning("模型不支持 tool calling，降级为纯文本：%s", e)
                payload.pop("tools", None)
                payload.pop("tool_choice", None)
                data = _post(base_url, api_key, "/chat/completions", payload, settings.llm_timeout)
            elif _fallback_ready():
                log.warning("主模型失败，降级 Ollama：%s", e)
                fallback = True
                name, mdl = "ollama", settings.fallback_model
                payload["model"] = mdl
                data = _post(
                    settings.fallback_base_url, "ollama", "/chat/completions", payload, settings.llm_timeout
                )
            else:
                raise LLMError(f"模型调用失败：{e}") from e

    msg = (data.get("choices") or [{}])[0].get("message") or {}
    usage = _usage(data.get("usage"))
    latency = int((time.perf_counter() - started) * 1000)
    _record(name, mdl, usage, scope, latency)
    result = LLMResult(
        content=(msg.get("content") or "").strip(),
        tool_calls=_normalize_calls(msg.get("tool_calls")),
        usage=usage,
        provider=name,
        model=mdl,
        latency_ms=latency,
        fallback=fallback,
    )
    log.info(
        "llm %s/%s %dms tokens=%d tool_calls=%d%s",
        result.provider,
        result.model,
        result.latency_ms,
        usage["total_tokens"],
        len(result.tool_calls),
        " (fallback)" if fallback else "",
    )
    return result


def _normalize_calls(raw: list[dict] | None) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for i, call in enumerate(raw or []):
        fn = call.get("function") or {}
        name = fn.get("name") or ""
        if not name:
            continue
        args = fn.get("arguments")
        if isinstance(args, str):
            try:
                args = json.loads(args) if args.strip() else {}
            except json.JSONDecodeError:
                log.warning("工具参数不是合法 JSON：%s", args[:120])
                args = {}
        out.append(
            {
                "id": call.get("id") or f"call-{i}",
                "name": name,
                "arguments": args if isinstance(args, dict) else {},
            }
        )
    return out


def chat(
    messages: list[dict[str, Any]],
    temperature: float | None = None,
    tools: list[dict] | None = None,
    model: str | None = None,
    scope: str = "chat",
) -> str:
    """只取文本内容；保留给记忆抽取等简单场景。"""
    return complete(messages, tools=tools, temperature=temperature, model=model, scope=scope).content


# ---------------------------------------------------------------- 向量化
def embed(texts: list[str]) -> list[list[float]]:
    """向量化；维度必须与 LanceDB 表一致（settings.embed_dim）。"""
    if not texts:
        return []
    payload = {"model": settings.embed_model, "input": texts}
    try:
        with gate():
            data = _post(settings.embed_base_url, settings.embed_api_key, "/embeddings", payload, 60)
    except Exception as e:  # noqa: BLE001
        raise LLMError(f"向量化失败（检查 Ollama / bge-m3 是否就绪）：{e}") from e
    return [item["embedding"] for item in data["data"]]


def probe() -> dict[str, Any]:
    """设置页「测试连接」：只做最小对话。"""
    try:
        r = complete([{"role": "user", "content": "回复 ok"}], temperature=0, scope="probe")
        return {"ok": True, "provider": r.provider, "model": r.model, "reply": r.content[:40]}
    except Exception as e:  # noqa: BLE001
        return {"ok": False, "provider": settings.llm_provider, "error": str(e)[:300]}
