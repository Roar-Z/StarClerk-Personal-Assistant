"""安装动作：拷文件、建快捷方式、写卸载信息。

拆成三步给界面调，这样右上角的进度条能一格一格走，
哪步报错也能说清楚是卡在什么地方。
"""
from __future__ import annotations

import json
import shutil
import subprocess
import winreg
from pathlib import Path

from . import paths

CREATE_NO_WINDOW = 0x08000000
UNINST_KEY = r"Software\Microsoft\Windows\CurrentVersion\Uninstall\StarClerk"
RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"
STEPS = ("files", "shortcuts", "registry")


def _bad(path: Path) -> str:
    """明显不能装的目录先挡掉，别等拷一半再报错。"""
    try:
        p = path.resolve()
    except OSError:
        return "这个路径解析不了"
    if not p.is_absolute():
        return "请填完整路径，比如 D:\\Apps\\StarClerk"
    if p == Path(p.anchor):
        return "不能直接装在盘符根目录"
    if len(p.parts) <= 2:
        return "目录层级太浅，建议再套一层文件夹"
    if p == Path.home().resolve():
        return "不能直接装在用户目录下"
    banned = {"windows", "system32", "program files", "program files (x86)"}
    if p.name.lower() in banned:
        return "这个目录是系统占用的，换一个吧"
    if any(ch in str(p) for ch in '<>|"*?'):
        return "路径里有不能用的字符"
    return ""


def check(target: str) -> dict:
    """下一步之前先校验，顺便告诉用户要占多少空间。"""
    raw = (target or "").strip().strip('"')
    if not raw:
        return {"ok": False, "message": "先填一个安装目录"}
    p = Path(raw)
    msg = _bad(p)
    if msg:
        return {"ok": False, "message": msg}

    payload = paths.payload_dir()
    need = paths.size_of(payload)
    free = paths.free_space(p)
    if need and free and free < need * 1.2:
        return {"ok": False, "message": f"{p.anchor} 剩余空间不够，至少要 {paths.human(int(need * 1.2))}"}

    exists = p.is_dir() and any(p.iterdir())
    return {
        "ok": True,
        "message": "这个目录里已经有文件，会直接覆盖安装" if exists else "",
        "exists": exists,
        "target": str(p),
        "need_text": paths.human(need),
        "free_text": paths.human(free),
    }


def _copy_files(target: Path) -> str:
    payload = paths.payload_dir()
    if not payload.is_dir():
        raise RuntimeError("安装包不完整，找不到 app 目录")
    target.mkdir(parents=True, exist_ok=True)
    n = 0
    for src in payload.rglob("*"):
        if not src.is_file():
            continue
        dst = target / src.relative_to(payload)
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dst)
        n += 1
    if not n:
        raise RuntimeError("安装包里没有可安装的文件")
    return f"复制了 {n} 个文件"


def _lnk(lnk: Path, target: Path) -> None:
    """建快捷方式用系统自带的 WScript.Shell，省得再装 pywin32。"""
    lnk.parent.mkdir(parents=True, exist_ok=True)
    ps = (
        "$s=(New-Object -ComObject WScript.Shell).CreateShortcut('{lnk}');"
        "$s.TargetPath='{exe}';$s.WorkingDirectory='{cwd}';$s.Save()"
    ).format(lnk=lnk, exe=target, cwd=target.parent)
    subprocess.run(
        ["powershell", "-NoProfile", "-NonInteractive", "-Command", ps],
        capture_output=True,
        timeout=25,
        creationflags=CREATE_NO_WINDOW,
    )


def _shortcuts(target: Path, want_desktop: bool, want_menu: bool) -> str:
    exe = target / paths.APP_EXE
    made = []
    if want_desktop:
        desk = Path.home() / "Desktop"
        if not desk.is_dir():
            desk = Path.home() / "OneDrive" / "Desktop"
        if desk.is_dir():
            _lnk(desk / f"{paths.APP_NAME}.lnk", exe)
            made.append("桌面")
    if want_menu:
        menu = Path.home() / "AppData" / "Roaming" / "Microsoft" / "Windows" / "Start Menu" / "Programs"
        if menu.is_dir():
            _lnk(menu / f"{paths.APP_NAME}.lnk", exe)
            made.append("开始菜单")
    return "创建了 " + "、".join(made) + "快捷方式" if made else "没有创建快捷方式"


def _registry(target: Path, autostart: bool) -> str:
    exe = target / paths.APP_EXE
    uninst = target / paths.UNINST_EXE
    uninstall_cmd = f'"{uninst}"' if uninst.is_file() else f'"{exe}"'
    with winreg.CreateKey(winreg.HKEY_CURRENT_USER, UNINST_KEY) as k:
        winreg.SetValueEx(k, "DisplayName", 0, winreg.REG_SZ, paths.APP_NAME)
        winreg.SetValueEx(k, "DisplayVersion", 0, winreg.REG_SZ, paths.APP_VERSION)
        winreg.SetValueEx(k, "InstallLocation", 0, winreg.REG_SZ, str(target))
        winreg.SetValueEx(k, "DisplayIcon", 0, winreg.REG_SZ, str(exe))
        winreg.SetValueEx(k, "UninstallString", 0, winreg.REG_SZ, uninstall_cmd)
        winreg.SetValueEx(k, "NoModify", 0, winreg.REG_DWORD, 1)
        winreg.SetValueEx(k, "NoRepair", 0, winreg.REG_DWORD, 1)

    with winreg.CreateKey(winreg.HKEY_CURRENT_USER, RUN_KEY) as k:
        if autostart:
            winreg.SetValueEx(k, paths.APP_NAME, 0, winreg.REG_SZ, f'"{exe}"')
        else:
            try:
                winreg.DeleteValue(k, paths.APP_NAME)
            except FileNotFoundError:
                pass
    return "已登记到应用列表" + ("，并设为开机启动" if autostart else "")


def install(target: str, options: dict, step: str) -> dict:
    """一步一调，前端按 STEPS 顺序走。"""
    t = Path(target)
    if step not in STEPS:
        return {"ok": False, "message": f"未知步骤：{step}"}
    try:
        if step == "files":
            message = _copy_files(t)
            (t / "install.json").write_text(
                json.dumps({"version": paths.APP_VERSION, "path": str(t)}, ensure_ascii=False),
                encoding="utf-8",
            )
        elif step == "shortcuts":
            message = _shortcuts(t, options.get("desktop", True), options.get("menu", True))
        else:
            message = _registry(t, bool(options.get("autostart", False)))
    except Exception as e:  # noqa: BLE001  出错就把原因原样给界面
        return {"ok": False, "message": str(e)}
    return {"ok": True, "step": step, "message": message}


def launch(target: str) -> dict:
    exe = Path(target) / paths.APP_EXE
    if not exe.is_file():
        return {"ok": False, "message": "找不到 StarClerk.exe"}
    subprocess.Popen([str(exe)], cwd=str(exe.parent), close_fds=True)
    return {"ok": True}
