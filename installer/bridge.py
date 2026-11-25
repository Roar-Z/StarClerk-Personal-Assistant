"""安装向导的页面接口，方法尽量少，返回值统一用 dict。"""
from __future__ import annotations

from . import paths, setup


class Api:
    def __init__(self) -> None:
        # 下划线开头，pywebview 不会去反射它
        self._window = None

    def info(self) -> dict:
        payload = paths.payload_dir()
        default = str(paths.default_target())
        return {
            "app": paths.APP_NAME,
            "version": paths.APP_VERSION,
            "default_dir": default,
            "need_text": paths.human(paths.size_of(payload)),
            "free_text": paths.human(paths.free_space(paths.default_target())),
            "payload_ok": paths.has_payload(),
            "payload_dir": str(payload),
        }

    def pick_dir(self, current: str = "") -> dict:
        """调系统的选目录框，pywebview 自带，不用自己写 shell。"""
        if self._window is None:
            return {"ok": False, "message": "窗口还没准备好"}
        import webview

        start = current or str(paths.default_target())
        picked = self._window.create_file_dialog(webview.FOLDER_DIALOG, directory=start)
        if not picked:
            return {"ok": False, "cancelled": True}
        return {"ok": True, "path": str(picked[0])}

    def check(self, target: str) -> dict:
        return setup.check(target)

    def install(self, target: str, options: dict, step: str) -> dict:
        return setup.install(target, options or {}, step)

    def launch(self, target: str) -> dict:
        return setup.launch(target)

    def close(self) -> bool:
        if self._window is not None:
            self._window.destroy()
        return True
