"""全局配置：单一来源，来自 .env（PyInstaller 打包后读取 EXE 同目录 .env）。"""
from __future__ import annotations

import os
import sys
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


def base_dir() -> Path:
    """源码运行取仓库根目录；打包后取 EXE 所在目录（数据与配置不写进临时解包目录）。"""
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=str(base_dir() / ".env"), env_file_encoding="utf-8", extra="ignore"
    )

    app_host: str = "127.0.0.1"
    app_port: int = 8756
    data_dir: str = "./data"

    llm_provider: str = "deepseek"
    llm_base_url: str = "https://api.deepseek.com/v1"
    llm_api_key: str = ""
    llm_model: str = "deepseek-chat"
    llm_temperature: float = 0.5
    llm_timeout: float = 60

    embed_provider: str = "ollama"
    embed_base_url: str = "http://127.0.0.1:11434/v1"
    embed_api_key: str = "ollama"
    embed_model: str = "bge-m3"
    embed_dim: int = 1024

    fallback_enabled: bool = True
    fallback_base_url: str = "http://127.0.0.1:11434/v1"
    fallback_model: str = "qwen2.5:7b"

    # ---- Agent ----
    agent_max_steps: int = 3  # ReAct 最多思考几轮（含首轮）
    agent_memory_top_k: int = 4  # 每轮思考前召回的记忆条数
    web_search_enabled: bool = True
    tavily_api_key: str = ""  # 留空则用 DuckDuckGo HTML
    web_search_timeout: float = 12
    patrol_allow_web: bool = False  # 后台巡检默认不联网，避免定时任务频繁出网

    # ---- 托管任务 ----
    plan: str = "free"  # free | pro（首次启动写入 kv，可通过 /api/config/plan 切换）
    free_task_limit: int = 5
    pro_task_limit: int = 20
    scheduler_enabled: bool = True
    scheduler_interval: int = 20  # 子线程轮询间隔（秒）

    hotkey: str = "<ctrl>+<alt>+<space>"
    tray_enabled: bool = True
    window_mode: str = "webview"  # webview | browser | none

    @property
    def root(self) -> Path:
        return base_dir()

    @property
    def data_path(self) -> Path:
        p = Path(self.data_dir)
        p = (self.root / p) if not p.is_absolute() else p
        p.mkdir(parents=True, exist_ok=True)
        return p

    @property
    def db_path(self) -> Path:
        return self.data_path / "starcLerk.db"

    @property
    def lancedb_path(self) -> Path:
        d = self.data_path / "lancedb"
        d.mkdir(parents=True, exist_ok=True)
        return d

    @property
    def upload_path(self) -> Path:
        d = self.data_path / "uploads"
        d.mkdir(parents=True, exist_ok=True)
        return d

    @property
    def static_path(self) -> Path:
        """前端构建产物：打包时随 EXE 放在 _MEIPASS 下。"""
        if getattr(sys, "frozen", False):
            return Path(getattr(sys, "_MEIPASS", self.root)) / "frontend_dist"
        return self.root / "frontend" / "dist"


settings = Settings()
os.environ.setdefault("TQDM_DISABLE", "1")
