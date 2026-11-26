"""教务课表本地存储：只存广科这一所，导入结果放 kv 表。"""
from __future__ import annotations

from typing import Any

from ..db import models as meta

KEY_COURSES = "eas.gdust.courses"
KEY_AT = "eas.gdust.at"


def courses() -> list[dict[str, Any]]:
    v = meta.kv_get(KEY_COURSES, [])
    return v if isinstance(v, list) else []


def save(items: list[dict[str, Any]]) -> None:
    import time

    meta.kv_set(KEY_COURSES, items)
    meta.kv_set(KEY_AT, time.time())


def clear() -> None:
    meta.kv_set(KEY_COURSES, [])
    meta.kv_set(KEY_AT, 0)


def info() -> dict[str, Any]:
    return {"count": len(courses()), "at": meta.kv_get(KEY_AT, 0)}
