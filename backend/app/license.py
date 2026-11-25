"""本机登录状态：未登录 guest / 已登录 free，两态，不联网。

内部还沿用 guest/free 这两个名字，界面上只说未登录和已登录。
两层存储，各有用途：
- SQLite 的 license 表是真状态，登录退出都走它；
- data/license.json 是给人看的备份，拷到另一台机器也能读到登录状态，
  所以启动时先读库，库里是空的再读这份 json 兜底。
"""
from __future__ import annotations

import hashlib
import json
import logging
import platform
import threading
from pathlib import Path
from typing import Any

from .config import settings
from .db import models as meta

log = logging.getLogger("license")

TIERS = ("guest", "free")
RANK = {"guest": 0, "free": 1}


def _normalize_tier(value: Any) -> str:
    """老库里可能还存着 pro，读出来一律按已登录算。"""
    t = str(value or "").strip().lower()
    if t == "pro":
        return "free"
    return t if t in TIERS else "guest"

# 并发上限写死 2：本地机器上再多线程一起打模型，显存和响应都会炸
MAX_CONCURRENCY = 2

_lock = threading.RLock()  # login 里会再次进 _state，必须是可重入锁
_cache: dict[str, Any] = {}


def _machine() -> str:
    """机器指纹只做展示，不参与校验——换电脑重新登录一下就行。"""
    raw = f"{platform.node()}|{platform.machine()}|{settings.data_dir}"
    return hashlib.md5(raw.encode("utf-8")).hexdigest()[:10]


# ---------------------------------------------------------------- 读写
def _json_path() -> Path:
    return settings.data_path / "license.json"


def _dump_json(state: dict[str, Any]) -> None:
    try:
        _json_path().write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")
    except OSError as e:  # 磁盘只读之类的情况，库里有就行
        log.warning("授权文件写入失败：%s", e)


def _from_json() -> dict[str, Any] | None:
    p = _json_path()
    if not p.is_file():
        return None
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    if not isinstance(data, dict):
        return None
    data["tier"] = _normalize_tier(data.get("tier"))
    return data


def _state() -> dict[str, Any]:
    """内存缓存 + 首次加载。进程内所有接口都读这一份，别每次查库。"""
    if _cache:
        return _cache
    with _lock:
        if _cache:
            return _cache
        row = meta.license_get()
        if row is None:
            # 全新的库（换电脑/第一次跑）：看看有没有人拷了一份 license.json 过来
            backup = _from_json()
            if backup and RANK.get(str(backup.get("tier")), 0) > 0:
                meta.license_set(
                    str(backup["tier"]),
                    str(backup.get("code") or ""),
                    str(backup.get("machine") or _machine()),
                )
                row = meta.license_get()
        row = row or {}
        raw = str(row.get("tier") or "guest").lower()
        if raw == "pro":
            # 老版本升级上来，库里那行 pro 就地改成 free，别把人踢回未登录
            meta.license_set("free", str(row.get("code") or ""), str(row.get("machine") or _machine()))
            row = meta.license_get() or row
            log.info("旧的 Pro 状态已转成已登录")
        _cache.update(
            {
                "tier": _normalize_tier(row.get("tier")),
                "code": row.get("code") or "",
                "machine": row.get("machine") or _machine(),
                "activated_at": float(row.get("activated_at") or 0),
                "perf_mode": bool((_from_json() or {}).get("perf_mode")),
                "max_concurrency": MAX_CONCURRENCY,
            }
        )
        if raw == "pro":
            _dump_json(_cache)
        return _cache


def tier() -> str:
    return _state()["tier"]


def rank() -> int:
    return RANK[tier()]


def is_guest() -> bool:
    return rank() == 0


def perf_mode() -> bool:
    return bool(_state()["perf_mode"])


def login() -> dict[str, Any]:
    """本机登录：不联网、不要密码，点一下就记在本地。"""
    mark = "LOCAL-" + _machine()[:6].upper()
    with _lock:
        meta.license_set("free", mark, _machine())
        _cache.clear()
        _dump_json(_state())
    log.info("本机登录成功")
    return info()


def logout() -> dict[str, Any]:
    """退出登录，留着方便自己试未登录时有哪些限制。"""
    with _lock:
        meta.license_clear(_machine())
        _cache.clear()
        state = _state()
        _dump_json(state)
    log.info("已退出登录")
    return info()


def set_perf(on: bool) -> dict[str, Any]:
    state = _state()
    state["perf_mode"] = bool(on)
    _dump_json(state)
    return info()


def info() -> dict[str, Any]:
    from .access import limits_for

    state = _state()
    limits = limits_for(state["tier"])
    return {
        "tier": state["tier"],
        "label": {"guest": "未登录", "free": "已登录"}[state["tier"]],
        "is_guest": state["tier"] == "guest",
        "is_logged_in": state["tier"] == "free",
        "mark": state["code"],
        "logged_in_at": state["activated_at"],
        "machine": state["machine"],
        "perf_mode": state["perf_mode"],
        "max_concurrency": state["max_concurrency"],
        "limits": limits,
    }
