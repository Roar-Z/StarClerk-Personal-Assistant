"""数据迁移：把 data 目录里的东西打成一个 zip，换电脑后导回去。

只搬 SQLite 和授权文件，向量库和上传的附件太大，单独拷 data 目录更快，
向导里也写清楚了。导入前会把现有库备份一份，手滑了还能捞回来。
"""
from __future__ import annotations

import json
import shutil
import time
import zipfile
from pathlib import Path

from fastapi import APIRouter, File, HTTPException, UploadFile
from fastapi.responses import FileResponse

from .. import license
from ..config import settings
from ..db import models

router = APIRouter(prefix="/migrate", tags=["migrate"])


def _data() -> Path:
    return Path(settings.data_path)


def _backup_dir() -> Path:
    d = _data() / "backup"
    d.mkdir(parents=True, exist_ok=True)
    return d


@router.get("/info", summary="当前数据量")
def info():
    return {
        "data_dir": str(_data()),
        "db": str(settings.db_path),
        "size": Path(settings.db_path).stat().st_size if Path(settings.db_path).is_file() else 0,
        "counts": {
            "sessions": len(models.list_sessions(1000)),
            "notes": models.count_notes(),
            "skills": models.count_skills(),
            "memories": models.count_memories(),
            "tasks": len(models.list_tasks()),
        },
        "tier": license.tier(),
        "backups": sorted(p.name for p in _backup_dir().glob("*.db"))[-5:],
    }


@router.get("/export", summary="打包导出")
def export_pack():
    """线上直接 download 就行，zip 里就两三个文件。"""
    out = _backup_dir() / f"starc-migrate-{time.strftime('%Y%m%d-%H%M%S')}.zip"
    manifest = {
        "app": "StarClerk",
        "version": 1,
        "created_at": time.strftime("%Y-%m-%d %H:%M:%S"),
        "tier": license.tier(),
        "counts": {
            "notes": models.count_notes(),
            "skills": models.count_skills(),
            "memories": models.count_memories(),
            "tasks": len(models.list_tasks()),
        },
    }
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as z:
        db_path = Path(settings.db_path)
        if db_path.is_file():
            z.write(db_path, db_path.name)
        lic = _data() / "license.json"
        if lic.is_file():
            z.write(lic, "license.json")
        z.writestr("manifest.json", json.dumps(manifest, ensure_ascii=False, indent=2))
    return FileResponse(out, filename=out.name, media_type="application/zip")


@router.post("/import", summary="导入迁移包")
async def import_pack(file: UploadFile = File(...)):
    raw = await file.read()
    if len(raw) > 200 * 1024 * 1024:
        raise HTTPException(400, "包太大了，超过 200MB，直接拷 data 目录吧")
    tmp = _data() / "_incoming"
    shutil.rmtree(tmp, ignore_errors=True)
    tmp.mkdir(parents=True, exist_ok=True)
    pack = tmp / "pack.zip"
    pack.write_bytes(raw)
    db_name = Path(settings.db_path).name

    try:
        with zipfile.ZipFile(pack) as z:
            names = set(z.namelist())
            if db_name not in names:
                raise HTTPException(400, f"包里没有 {db_name}，确认选的是迁移包")
            z.extractall(tmp)
    except zipfile.BadZipFile as e:
        raise HTTPException(400, "这个文件不是 zip") from e

    manifest: dict = {}
    if (tmp / "manifest.json").is_file():
        try:
            manifest = json.loads((tmp / "manifest.json").read_text(encoding="utf-8"))
        except ValueError:
            manifest = {}

    # 先留个旧库，别一覆盖就全没了
    old = Path(settings.db_path)
    if old.is_file():
        shutil.copyfile(old, _backup_dir() / f"before-import-{time.strftime('%Y%m%d-%H%M%S')}.db")
    # WAL 的边角文件不清掉，新库会被旧日志带偏
    for suffix in ("-wal", "-shm"):
        p = Path(str(old) + suffix)
        if p.is_file():
            p.unlink()
    shutil.copyfile(tmp / db_name, old)

    if (tmp / "license.json").is_file():
        shutil.copyfile(tmp / "license.json", _data() / "license.json")

    shutil.rmtree(tmp, ignore_errors=True)
    return {
        "ok": True,
        "restart": True,
        "from": manifest.get("created_at", ""),
        "counts": manifest.get("counts", {}),
        "msg": "导入好了，重启程序后生效；旧库已备份到 data/backup",
    }


@router.post("/cleanup", summary="清掉导入留下的临时文件")
def cleanup():
    shutil.rmtree(_data() / "_incoming", ignore_errors=True)
    return {"ok": True}
