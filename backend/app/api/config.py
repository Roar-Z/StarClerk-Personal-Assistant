"""config 分组：模型/向量/快捷键配置（写回 .env）、档位额度、连接测试。

授权相关的写操作都在 /api/license，这里只读。
"""
from __future__ import annotations

import asyncio
import os
from pathlib import Path

from fastapi import APIRouter
from pydantic import BaseModel

from .. import access, license, quota
from ..config import settings
from ..db import models as meta
from ..llm import client
from ..tasks.scheduler import runner
from ..vector import lancedb_store as vs
from .deps import failure

router = APIRouter(prefix="/config", tags=["config"])

EDITABLE = {
    "llm_provider": "LLM_PROVIDER",
    "llm_base_url": "LLM_BASE_URL",
    "llm_api_key": "LLM_API_KEY",
    "llm_model": "LLM_MODEL",
    "llm_gateway": "LLM_GATEWAY",
    "embed_base_url": "EMBED_BASE_URL",
    "embed_model": "EMBED_MODEL",
    "embed_dim": "EMBED_DIM",
    "fallback_enabled": "FALLBACK_ENABLED",
    "hotkey": "HOTKEY",
}


class ConfigIn(BaseModel):
    llm_provider: str | None = None
    llm_base_url: str | None = None
    llm_api_key: str | None = None
    llm_model: str | None = None
    llm_gateway: str | None = None
    embed_base_url: str | None = None
    embed_model: str | None = None
    embed_dim: int | None = None
    fallback_enabled: bool | None = None
    hotkey: str | None = None


@router.get("", summary="当前配置")
def get_config():
    return {
        "llm_provider": settings.llm_provider,
        "llm_base_url": settings.llm_base_url,
        "llm_model": settings.llm_model,
        "llm_gateway": settings.llm_gateway or "own",
        "llm_api_key_masked": ("***" + settings.llm_api_key[-4:]) if settings.llm_api_key else "",
        # 游客实际调的是这条，前端模型页拿它显示"当前免费模型"
        "guest_model": {
            "provider": client.GUEST_PROVIDER,
            "label": "Kilo 免费",
            "base_url": settings.guest_llm_base_url,
            "model": settings.guest_llm_model,
            "hourly": quota.limit(),
        },
        "embed_base_url": settings.embed_base_url,
        "embed_model": settings.embed_model,
        "embed_dim": settings.embed_dim,
        "fallback_enabled": settings.fallback_enabled,
        "hotkey": settings.hotkey,
        "window_mode": settings.window_mode,
        "data_dir": str(settings.data_path),
        "providers": client.PROVIDERS,
        "plan": meta.plan_info(),
        "license": license.info(),
        "limits": {"free": access.LIMITS["free"]},
        "scheduler": {**runner.status(), "enabled": settings.scheduler_enabled},
    }


def _write_env(updates: dict[str, str]) -> None:
    env_path = Path(settings.root) / ".env"
    lines = env_path.read_text(encoding="utf-8").splitlines() if env_path.exists() else []
    left = [ln for ln in lines if ln.split("=", 1)[0].strip() not in updates]
    left += [f"{k}={v}" for k, v in updates.items()]
    env_path.write_text("\n".join(left) + "\n", encoding="utf-8")


@router.put("", summary="保存配置（写回 .env，重启生效）")
def update(body: ConfigIn):
    data = body.model_dump(exclude_none=True)
    updates: dict[str, str] = {}
    for field, value in data.items():
        env_key = EDITABLE.get(field)
        if not env_key:
            continue
        setattr(settings, field, value)
        updates[env_key] = str(value)
        os.environ[env_key] = str(value)
    if updates:
        _write_env(updates)
    vector_changed = any(k in updates for k in ("EMBED_MODEL", "EMBED_DIM"))
    return {"ok": True, "need_rebuild_vector": vector_changed}


@router.get("/providers", summary="可选服务商预设")
def providers():
    return client.PROVIDERS


@router.get("/plan", summary="当前档位与任务额度（只读）")
def plan():
    return meta.plan_info()


@router.post("/test", summary="测试模型连接")
async def test_llm():
    return await asyncio.to_thread(client.probe)


@router.post("/rebuild-vector", summary="重建向量索引")
async def rebuild_vector():
    try:
        await asyncio.to_thread(vs.reset)
    except Exception as e:  # noqa: BLE001
        raise failure("config", e) from e
    return {"ok": True}
