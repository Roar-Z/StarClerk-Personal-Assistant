"""技能模板：一段带 {input} 的提示词，点一下就把内容填进输入框。

内置那几条是种子数据，第一次打开时写进库。用户改过的模板不会被重新覆盖。
导入导出用 JSON，图省事，反正就自己用。
"""
from __future__ import annotations

import json

from fastapi import APIRouter, HTTPException, Response
from pydantic import BaseModel, Field

from ..db import models

router = APIRouter(prefix="/skills", tags=["skills"])


class SkillIn(BaseModel):
    name: str = Field(min_length=1, max_length=40)
    category: str = Field(default="通用", max_length=20)
    body: str = Field(min_length=5, max_length=8000)


class SkillPatch(BaseModel):
    name: str | None = None
    category: str | None = None
    body: str | None = None


class SkillImport(BaseModel):
    items: list[SkillIn]


@router.get("", summary="模板列表")
def list_skills(category: str = ""):
    models.seed_skills()
    items = models.list_skills(category)
    cats = sorted({s["category"] for s in models.list_skills()})
    return {"items": items, "categories": cats, "total": models.count_skills()}


@router.post("", summary="新建模板")
def add_skill(body: SkillIn):
    return models.create_skill(body.name.strip(), body.category.strip() or "通用", body.body)


@router.put("/{sid}", summary="改模板")
def save_skill(sid: str, body: SkillPatch):
    if models.get_skill(sid) is None:
        raise HTTPException(404, "这个模板不存在")
    return models.update_skill(sid, **body.model_dump(exclude_unset=True))


@router.delete("/{sid}", summary="删模板")
def remove_skill(sid: str):
    models.delete_skill(sid)
    return {"ok": True}


@router.post("/{sid}/use", summary="取出来用一次")
def use_skill(sid: str):
    """只是把计数加一，真正的填空在前端做。"""
    skill = models.get_skill(sid)
    if skill is None:
        raise HTTPException(404, "这个模板不存在")
    models.bump_skill(sid)
    return skill


@router.get("/export", summary="导出全部模板")
def export_skills():
    items = [
        {"name": s["name"], "category": s["category"], "body": s["body"]}
        for s in models.list_skills()
    ]
    raw = json.dumps({"app": "StarClerk", "version": 1, "items": items}, ensure_ascii=False, indent=2)
    return Response(
        content=raw,
        media_type="application/json; charset=utf-8",
        headers={"Content-Disposition": 'attachment; filename="skills.json"'},
    )


@router.post("/import", summary="导入模板")
def import_skills(body: SkillImport):
    added = 0
    for item in body.items:
        models.create_skill(item.name.strip(), item.category.strip() or "通用", item.body)
        added += 1
    return {"ok": True, "added": added}
