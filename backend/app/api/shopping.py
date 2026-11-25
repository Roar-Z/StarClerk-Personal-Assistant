"""采购清单合并：把几条零散备忘按地点并成一张顺路清单。

不调模型，纯规则：数量能认出来就相加，认不出来就保留原词。
"""
from __future__ import annotations

import re
from typing import Any

from fastapi import APIRouter
from pydantic import BaseModel, Field

router = APIRouter(prefix="/shopping", tags=["shopping"])

PLACES = ["超市", "菜市场", "水果店", "便利店", "药房", "商场", "线上", "其他"]
_PLACE_WORDS = {
    "超市": ("超市", "沃尔玛", "永辉", "大润发", "盒马", "山姆"),
    "菜市场": ("菜市场", "菜场", "菜市"),
    "水果店": ("水果店", "果店", "水果摊"),
    "便利店": ("便利店", "小卖部", "7-11", "全家", "罗森"),
    "药房": ("药房", "药店", "大药房"),
    "商场": ("商场", "购物中心", "万达", "商场里"),
    "线上": ("京东", "淘宝", "拼多多", "外卖", "网上", "快递"),
}
_UNIT = r"(?:个|只|斤|瓶|盒|袋|件|包|箱|根|把|张|本|支|块|条|份|kg|g)"
_QTY_FRONT = re.compile(rf"^(\d+(?:\.\d+)?)\s*{_UNIT}\s*(.+)$")
_QTY_BACK = re.compile(rf"^(.+?)\s*[xX×*]?\s*(\d+(?:\.\d+)?)\s*{_UNIT}?$")
_CN_NUM = {"一": 1, "两": 2, "二": 2, "三": 3, "四": 4, "五": 5, "六": 6, "七": 7, "八": 8, "九": 9, "十": 10}


class ItemIn(BaseModel):
    text: str = Field(min_length=1, max_length=200)
    id: str = ""


class MergeIn(BaseModel):
    items: list[ItemIn] = Field(default_factory=list, max_length=100)


def _place(text: str) -> str:
    m = re.search(r"在([^\s，,；;]{1,10})(?:买|购|拿)", text)
    if m:
        return m.group(1)
    for place, words in _PLACE_WORDS.items():
        if any(w in text for w in words):
            return place
    return "其他"


def _split(text: str) -> tuple[str, float]:
    s = text.strip().strip("-•· ").strip()
    s = re.sub(r"在[^\s，,；;]{1,10}(?:买|购|拿)", "", s)
    for words in _PLACE_WORDS.values():
        for w in words:
            s = s.replace(w, "")
    s = re.sub(r"^(帮我|记得|要|需要|买|购入|采购)\s*", "", s)
    s = s.strip()
    m = _QTY_FRONT.match(s)
    if m:
        return m.group(2).strip(), float(m.group(1))
    m = _QTY_BACK.match(s)
    if m and m.group(1).strip():
        return m.group(1).strip(), float(m.group(2))
    m = re.match(rf"^([一两二三四五六七八九十\d]+)\s*{_UNIT}\s*(.+)$", s)
    if m:
        word = m.group(1)
        return m.group(2).strip(), float(_CN_NUM.get(word, word if word.isdigit() else 1))
    return s, 1.0


def _fmt_qty(n: float) -> str:
    return str(int(n)) if float(n).is_integer() else str(n)


@router.post("/merge", summary="合并采购备忘")
def merge(body: MergeIn):
    buckets: dict[str, dict[str, dict[str, Any]]] = {p: {} for p in PLACES}
    used = 0
    for i, raw in enumerate(body.items):
        line = raw.text.strip()
        if not line:
            continue
        used += 1
        place = _place(line)
        name, qty = _split(line)
        if not name:
            continue
        bucket = buckets.setdefault(place, {})
        if name in bucket:
            bucket[name]["qty"] += qty
            bucket[name]["sources"].append(raw.id or str(i + 1))
        else:
            bucket[name] = {"name": name, "qty": qty, "sources": [raw.id or str(i + 1)]}

    groups = []
    out = []
    for place in PLACES:
        items = list(buckets.get(place, {}).values())
        if not items:
            continue
        groups.append({"place": place, "items": items})
        out.append(f"【{place}】")
        out.extend(f"- {x['name']} ×{_fmt_qty(x['qty'])}" for x in items)
    return {"groups": groups, "text": "\n".join(out), "used": used}
