"""本地授权：未登录 guest / 免费版 free 两档，纯离线校验，不联网。

两层存储，各有用途：
- SQLite 的 license 表是"真的状态"，接口增删改都走它；
- data/license.json 是给人看的备份，把文件拷到另一台机器也能读到档位，
  所以启动时先读库，库里是空的再读这份 json 兜底。

激活码格式：FREE-XXXXXX-YYYY
YYYY 是用固定盐算出来的 4 位校验码，所以码不能随便改字母，但也不需要联网。
老版本签过的 PRO 码照样收，统一当免费版处理。
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
    """老库里可能还存着 pro，读出来一律按免费版算。"""
    t = str(value or "").strip().lower()
    if t == "pro":
        return "free"
    return t if t in TIERS else "guest"

# 并发上限写死 2：本地机器上再多线程一起打模型，显存和响应都会炸
MAX_CONCURRENCY = 2
_SALT = "starc2026"

_lock = threading.RLock()  # activate 里会再次进 _state，必须是可重入锁
_cache: dict[str, Any] = {}


# ---------------------------------------------------------------- 激活码
def _sign(body: str) -> str:
    raw = f"{body}:{_SALT}".encode("utf-8")
    return hashlib.sha1(raw).hexdigest()[:4].upper()


def make_code(tier: str = "free", seed: str = "000000") -> str:
    """生成一个可用的激活码，自己测试和 README 举例都用它。

    现在只有免费版，传什么 tier 都是 FREE 码，参数留着是怕老脚本还这么调。
    """
    body = f"FREE-{seed.upper()}"
    return f"{body}-{_sign(body)}"


def free_code() -> str:
    """一键免费激活用的码，跟机器码绑一下，只是看着像回事，不联网也不校验机器。"""
    return make_code("free", seed=_machine()[:6])


def parse_code(code: str) -> str | None:
    """校验码通过就返回档位，否则 None。"""
    text = (code or "").strip().upper()
    parts = text.split("-")
    if len(parts) != 3:
        return None
    tier, seed, sign = parts
    if tier not in ("FREE", "PRO") or len(seed) < 4:
        return None
    if sign != _sign(f"{tier}-{seed}"):
        return None
    return "free"  # PRO 老码也按免费版认，别让人升级之后用不了


def _machine() -> str:
    """机器指纹只做展示，不参与校验——换电脑重新激活一下就行。"""
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
            log.info("旧的 Pro 授权已转成免费版")
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


def activate(code: str) -> dict[str, Any]:
    parsed = parse_code(code)
    if not parsed:
        raise ValueError("激活码不对，检查一下是不是少了几位")
    with _lock:
        meta.license_set(parsed, code.strip().upper(), _machine())
        _cache.clear()
        _dump_json(_state())
    log.info("本地激活成功：%s", parsed)
    return info()


def reset() -> dict[str, Any]:
    """退回未登录，方便自己试两档的区别。"""
    with _lock:
        meta.license_clear(_machine())
        _cache.clear()
        state = _state()
        _dump_json(state)
    log.info("已退回游客模式")
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
        "label": {"guest": "未登录", "free": "免费版"}[state["tier"]],
        "is_guest": state["tier"] == "guest",
        "is_free": state["tier"] == "free",
        "code": state["code"],
        "activated_at": state["activated_at"],
        "machine": state["machine"],
        "perf_mode": state["perf_mode"],
        "max_concurrency": state["max_concurrency"],
        "limits": limits,
    }
