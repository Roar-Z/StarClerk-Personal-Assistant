"""本地 OCR：rapidocr-onnxruntime，纯 CPU、不联网，模型随包走。

第一次识别时才加载模型，不然只是开个软件也要等一两秒。
识别结果除了整段文字，还留着每一行，快递单和小票要按行找字段。
"""
from __future__ import annotations

import base64
import logging
import re
import threading
from typing import Any

log = logging.getLogger("ocr")

_engine: Any = None
_lock = threading.Lock()


def _model() -> Any:
    global _engine
    if _engine is None:
        with _lock:
            if _engine is None:
                from rapidocr_onnxruntime import RapidOCR

                _engine = RapidOCR()
                log.info("本地 OCR 模型已加载")
    return _engine


def _bytes(image: str) -> bytes:
    raw = (image or "").strip()
    if raw.startswith("data:image/"):
        raw = raw.split(",", 1)[-1]
    try:
        return base64.b64decode(raw)
    except Exception as e:  # noqa: BLE001
        raise ValueError("图片数据不是合法的 base64") from e


def recognize_image(img: Any) -> dict[str, Any]:
    """传 OpenCV 图进来识别，PDF 扫描页直接复用这块。"""
    result, _ = _model()(img)
    lines = []
    for item in result or []:
        try:
            box, text, score = item[0], str(item[1]), float(item[2])
        except Exception:  # noqa: BLE001
            continue
        if not text.strip():
            continue
        lines.append(
            {
                "text": text.strip(),
                "score": round(score, 3),
                "box": [[int(p[0]), int(p[1])] for p in box],
            }
        )
    lines.sort(key=lambda x: (min(p[1] for p in x["box"]), min(p[0] for p in x["box"])))
    return {"text": "\n".join(x["text"] for x in lines), "lines": lines, "count": len(lines)}


def recognize(image: str) -> dict[str, Any]:
    import cv2
    import numpy as np

    data = _bytes(image)
    arr = np.frombuffer(data, dtype=np.uint8)
    img = cv2.imdecode(arr, cv2.IMREAD_COLOR)
    if img is None:
        raise ValueError("读不出这张图，换个格式试试")
    return recognize_image(img)


# ---------------------------------------------------------------- 快递单
_PICKUP = re.compile(r"(?:取件码|取货码|提货码|凭码|货号)\s*[:：#]?\s*([A-Za-z0-9\-–一-龥]{3,16})")
_DIGIT_CODE = re.compile(r"(?<!\d)(\d{3,6})[-－ ]?(\d{3,6})(?!\d)")
_TRACK = re.compile(r"\b([A-Z]{2,4}\d{8,14}|[A-Z]{1,2}\d{9,16})\b")
_BIG_NUM = re.compile(r"(?<!\d)(\d{11,20})(?!\d)")
_STATION = re.compile(r"(?:驿站|取件点|快递点|代收点|自提点|网点|地址)[:：]?\s*([^\n，,；;]{2,30})")


def parse_express(text: str) -> dict[str, Any]:
    pickup = ""
    m = _PICKUP.search(text)
    if m:
        pickup = m.group(1).strip("。.,，")
    if not pickup:
        m = _DIGIT_CODE.search(text)
        if m:
            pickup = m.group(1) + "-" + m.group(2)

    track = ""
    for pat in (_TRACK, _BIG_NUM):
        m = pat.search(text)
        if m:
            track = m.group(0)
            break

    station = ""
    m = _STATION.search(text)
    if m:
        station = m.group(1).strip()
    if not station:
        m = re.search(r"([^\n\d]{1,12}(?:驿站|快递点|代收点|自提点))", text)
        if m:
            station = m.group(1).strip()

    memo = "取快递"
    if pickup:
        memo += f"，取件码 {pickup}"
    if station:
        memo += f"，{station}"
    if track:
        memo += f"，单号 {track}"
    return {
        "kind": "express",
        "pickup_code": pickup,
        "tracking_no": track,
        "station": station,
        "memo": memo,
        "raw": text,
    }


# ---------------------------------------------------------------- 小票
_MONEY = re.compile(r"(?:合计|总计|实付|应付|总额|金额)\s*[:：]?\s*[¥￥]?\s*(\d+(?:\.\d{1,2})?)")
_DATE = re.compile(r"(20\d{2})[-/年.](\d{1,2})[-/月.](\d{1,2})")
_ITEM_PRICE = re.compile(r"(¥|￥)?\s*(\d+(?:\.\d{1,2})?)\s*$")


def parse_receipt(text: str, lines: list[str] | None = None) -> dict[str, Any]:
    rows = lines or [x.strip() for x in text.splitlines() if x.strip()]
    total = ""
    m = _MONEY.search(text)
    if m:
        total = m.group(1)

    date = ""
    m = _DATE.search(text)
    if m:
        date = f"{m.group(1)}-{int(m.group(2)):02d}-{int(m.group(3)):02d}"

    seller = ""
    for row in rows[:4]:
        if not _ITEM_PRICE.search(row) and len(row) >= 2 and not _DATE.search(row):
            seller = row
            break

    items = []
    for row in rows:
        p = _ITEM_PRICE.search(row)
        if not p:
            continue
        name = row[: p.start()].strip(" ·-—\t")
        if not name or any(k in name for k in ("合计", "总计", "实付", "金额", "找零", "收款")):
            continue
        items.append({"name": name, "price": p.group(2)})

    memo = f"{seller or '消费'} {total + ' 元' if total else ''}".strip()
    if date:
        memo += f"，{date}"
    return {
        "kind": "receipt",
        "seller": seller,
        "date": date,
        "total": total,
        "items": items,
        "memo": memo,
        "raw": text,
    }
