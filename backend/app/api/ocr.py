"""本地 OCR 接口：通用识字 + 快递单/小票专项。

图片在本机识别，不调云端模型，也不占游客的大模型额度。
"""
from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from .. import ocr

router = APIRouter(prefix="/ocr", tags=["ocr"])


class ImageIn(BaseModel):
    image: str = Field(min_length=32)


class ParseIn(BaseModel):
    image: str | None = None
    text: str = ""
    kind: str = "express"  # express | receipt


@router.post("/local", summary="本地通用识字")
def local(body: ImageIn):
    try:
        return ocr.recognize(body.image)
    except ValueError as e:
        raise HTTPException(400, str(e)) from e
    except Exception as e:  # noqa: BLE001
        raise HTTPException(500, f"本地 OCR 没跑起来：{e}") from e


@router.post("/parse", summary="快递单 / 小票专项识别")
def parse(body: ParseIn):
    text = body.text.strip()
    lines: list[str] = []
    if body.image and len(body.image) >= 32:
        try:
            hit = ocr.recognize(body.image)
            lines = [x["text"] for x in hit["lines"]]
            text = text or hit["text"]
        except ValueError as e:
            raise HTTPException(400, str(e)) from e
        except Exception as e:  # noqa: BLE001
            raise HTTPException(500, f"本地 OCR 没跑起来：{e}") from e
    if not text:
        raise HTTPException(400, "传张图片，或者直接把单子上的字贴进来")

    if body.kind == "receipt":
        return ocr.parse_receipt(text, lines)
    if body.kind == "express":
        return ocr.parse_express(text)
    raise HTTPException(400, "kind 只能是 express 或 receipt")
