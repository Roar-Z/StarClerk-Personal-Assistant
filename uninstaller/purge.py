"""扫描和真正删数据的地方。

删之前先跑一遍 scan 算体积，UI 上让用户看到"东西有多大、在哪"；
删的时候一项一项来，哪项失败就记下来，不能因为一个文件被占用就中断全部。
"""
from __future__ import annotations

import json
import shutil
import sqlite3
import subprocess
from pathlib import Path

from . import catalog, guard, paths

CREATE_NO_WINDOW = 0x08000000
DETACHED_PROCESS = 0x00000008


# ---------------------------------------------------------------- 体积与条数
def _count(sql: str) -> int:
    db = paths.db_file()
    if not db.is_file():
        return 0
    try:
        with sqlite3.connect(str(db), timeout=5) as c:
            row = c.execute(sql).fetchone()
        return int(row[0]) if row else 0
    except sqlite3.Error:
        return 0


def _log_files() -> list[Path]:
    d = paths.log_dir()
    if not d.is_dir():
        return []
    return [p for p in d.iterdir() if p.is_file()]


def _detail(key: str) -> tuple[int, str]:
    """返回 (字节数, 给人看的说明)，说明优先说条数，说不清就给大小。"""
    if key == "usage":
        n = _count("SELECT COUNT(*) FROM usage") + _count("SELECT COUNT(*) FROM errors")
        return 0, f"{n} 条统计记录" if n else "暂无记录"
    if key == "logs":
        fs = _log_files()
        size = sum(p.stat().st_size for p in fs if p.exists())
        return size, f"{len(fs)} 个文件 · {paths.human(size)}" if fs else "暂无日志"
    if key == "sessions":
        s, m = _count("SELECT COUNT(*) FROM sessions"), _count("SELECT COUNT(*) FROM messages")
        return 0, f"{s} 个会话 · {m} 条消息" if s or m else "暂无会话"
    if key == "tasks":
        t, r = _count("SELECT COUNT(*) FROM tasks"), _count("SELECT COUNT(*) FROM task_logs")
        return 0, f"{t} 个任务 · {r} 条运行记录" if t or r else "暂无任务"
    if key == "memory":
        n = _count("SELECT COUNT(*) FROM memories")
        size = paths.size_of(paths.lancedb_dir() / "memories.lance")
        return size, f"{n} 条记忆" if n else "暂无记忆"
    if key == "mindmaps":
        d = paths.data_dir() / "mindmaps"
        size = paths.size_of(d)
        n = len(list(d.iterdir())) if d.is_dir() else 0
        return size, f"{n} 个文件 · {paths.human(size)}" if n else "暂无导图"
    if key == "knowledge":
        size = paths.size_of(paths.lancedb_dir() / "documents.lance") + paths.size_of(paths.upload_dir())
        return size, paths.human(size) if size else "知识库是空的"
    if key == "config":
        env = paths.env_file()
        return paths.size_of(env), "有自定义配置" if env.is_file() else "使用默认配置"
    if key == "license":
        f = paths.license_file()
        state = "未登录"
        if f.is_file():
            try:
                tier = json.loads(f.read_text(encoding="utf-8")).get("tier", "guest")
                state = "已登录" if tier == "free" else "未登录"
            except (OSError, ValueError):
                pass
        return paths.size_of(f), f"当前状态：{state}"
    if key == "program":
        size = paths.size_of(paths.install_dir())
        return size, paths.human(size)
    return 0, ""


def scan() -> dict:
    frozen = paths.is_frozen()
    rows = []
    for it in catalog.items(frozen):
        size, detail = _detail(it["key"])
        rows.append({**it, "size": size, "detail": detail})
    total = sum(r["size"] for r in rows if r["key"] != "program")
    return {
        "items": rows,
        "install_dir": str(paths.install_dir()),
        "data_dir": str(paths.data_dir()),
        "log_dir": str(paths.log_dir()),
        "frozen": frozen,
        "data_total": total,
        "data_total_text": paths.human(total),
        "all_keys": catalog.data_keys(frozen),
        "guard": guard.status(),
    }


# ---------------------------------------------------------------- 删除
def _safe(path: Path) -> bool:
    """挡一下明显危险的目标：盘符根、用户目录、Windows/Program Files 这种。"""
    try:
        p = path.resolve()
    except OSError:
        return False
    if p == Path(p.anchor) or p == Path.home().resolve():
        return False
    if len(p.parts) <= 2:
        return False
    banned = {"windows", "program files", "program files (x86)", "users", "system32"}
    return p.name.lower() not in banned


def _rm(path: Path) -> int:
    """返回释放的字节数；路径不存在不算错。"""
    if not path.exists():
        return 0
    if not _safe(path):
        raise RuntimeError(f"路径看着不对，不敢删：{path}")
    size = paths.size_of(path)
    if path.is_dir():
        shutil.rmtree(path, ignore_errors=False)
    else:
        path.unlink()
    return size


def _rm_children(directory: Path) -> int:
    """目录本身留着（下次启动还要用），只清里面的东西。"""
    if not directory.is_dir():
        return 0
    freed = 0
    for child in directory.iterdir():
        freed += _rm(child)
    return freed


def _sql(*statements: str) -> None:
    db = paths.db_file()
    if not db.is_file():
        return
    with sqlite3.connect(str(db), timeout=10) as c:
        for sql in statements:
            c.execute(sql)
        c.commit()


def _vacuum() -> None:
    """删完表空间不会自动还回去，vacuum 一下文件才会变小。"""
    db = paths.db_file()
    if not db.is_file():
        return
    try:
        with sqlite3.connect(str(db), timeout=10) as c:
            c.execute("VACUUM")
    except sqlite3.Error:
        pass  # 库被占用就算了，数据已经删了


def _delete(key: str) -> str:
    """执行单项删除，返回一句结果说明给 UI 显示。"""
    if key == "usage":
        _sql("DELETE FROM usage", "DELETE FROM errors")
        return "用量和错误记录已清空"
    if key == "logs":
        n = len(_log_files())
        _rm_children(paths.log_dir())
        return f"删了 {n} 个日志文件"
    if key == "sessions":
        _sql("DELETE FROM messages", "DELETE FROM sessions")
        return "会话和消息已清空"
    if key == "tasks":
        _sql("DELETE FROM task_logs", "DELETE FROM tasks")
        return "任务和运行记录已清空"
    if key == "mindmaps":
        _rm(paths.data_dir() / "mindmaps")
        return "导图文件已删除"
    if key == "memory":
        _sql("DELETE FROM memories")
        # 记忆向量单独一个表，直接删表目录，下次连库会自动建空表
        _rm(paths.lancedb_dir() / "memories.lance")
        return "记忆和记忆向量已删除"
    if key == "knowledge":
        _rm(paths.lancedb_dir() / "documents.lance")
        _rm_children(paths.upload_dir())
        return "资料索引和上传文件已删除"
    if key == "config":
        _rm(paths.env_file())
        return ".env 已删除，下次启动用默认配置"
    if key == "license":
        _sql("DELETE FROM license")
        _rm(paths.license_file())
        return "登录信息已清除，已退出登录"
    if key == "program":
        links = [p for p in paths.shortcut_files() if p.is_file()]
        for p in links:
            _rm(p)
        # 卸载器自己也在安装目录里，只能等窗口退出再删
        _rm_later(paths.install_dir())
        if links:
            return f"桌面/开始菜单快捷方式（{len(links)} 个）已删除，程序目录在窗口关闭后删除"
        return "程序目录会在窗口关闭后删除"
    raise KeyError(key)


def _rm_later(target: Path) -> None:
    """卸载器自己也在这个目录里，只能先退出再让 cmd 延时删。"""
    cmd = f'ping -n 3 127.0.0.1 >nul & rmdir /s /q "{target}"'
    subprocess.Popen(
        ["cmd", "/c", cmd],
        creationflags=CREATE_NO_WINDOW | DETACHED_PROCESS,
        close_fds=True,
    )


def run(keys: list[str]) -> dict:
    frozen = paths.is_frozen()
    allowed = catalog.keys(frozen)
    picked = [k for k in allowed if k in set(keys)]  # 按 catalog 顺序来，program 一定最后
    if not picked:
        return {"ok": False, "message": "没有选中任何内容", "results": []}

    st = guard.status()
    if st["running"] and any(catalog.BY_KEY[k].needs_closed for k in picked):
        return {
            "ok": False,
            "need_stop": True,
            "message": "主程序还在运行，先关掉再删数据，不然库可能删坏",
            "results": [],
            "guard": st,
        }

    db_before = paths.size_of(paths.db_file())
    results = []
    freed = 0
    errors = 0
    touched_db = False
    for key in picked:
        item = catalog.BY_KEY[key]
        try:
            if key == "program":
                # 数据算完最后才动程序，连快捷方式一起收
                results.append({"key": key, "title": item.title, "ok": True,
                                "detail": _delete(key)})
                continue
            if key in {"usage", "sessions", "tasks", "memory", "license"}:
                touched_db = True
            freed += _delete_size(key)
            results.append({"key": key, "title": item.title, "ok": True, "detail": _delete(key)})
        except Exception as e:  # noqa: BLE001  单项失败不该把整批炸掉
            errors += 1
            results.append({"key": key, "title": item.title, "ok": False, "detail": str(e)})

    if touched_db:
        _vacuum()
        # 表里删掉的数据只有 vacuum 之后才会体现在文件大小上
        freed += max(0, db_before - paths.size_of(paths.db_file()))

    return {
        "ok": errors == 0,
        "results": results,
        "freed": freed,
        "freed_text": paths.human(freed),
        "need_exit": "program" in picked,
    }


def _delete_size(key: str) -> int:
    """删之前量一下，删完就量不到了。"""
    if key == "logs":
        return paths.size_of(paths.log_dir())
    if key == "memory":
        return paths.size_of(paths.lancedb_dir() / "memories.lance")
    if key == "knowledge":
        return paths.size_of(paths.lancedb_dir() / "documents.lance") + paths.size_of(paths.upload_dir())
    if key == "mindmaps":
        return paths.size_of(paths.data_dir() / "mindmaps")
    if key == "config":
        return paths.size_of(paths.env_file())
    if key == "license":
        return paths.size_of(paths.license_file())
    return 0
