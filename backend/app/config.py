"""全局配置：单一来源，来自 .env（PyInstaller 打包后读取 EXE 同目录 .env）。"""
from __future__ import annotations

import os
import sys
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

APP_NAME = "StarClerk"
APP_VERSION = "0.2.0"


def is_frozen() -> bool:
    """PyInstaller 打完包会把 sys.frozen 设上，用它分开源码和安装目录。"""
    return bool(getattr(sys, "frozen", False))


def base_dir() -> Path:
    """源码运行取仓库根目录；打包后取 EXE 所在目录，数据跟着程序走，不进 _MEIPASS。"""
    if is_frozen():
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

    # ---- 游客免费模型 ----
    # 游客不给选模型，统一走 Kilo 网关的免费档；这个档不用 Key，按 IP 限流
    guest_llm_base_url: str = "https://ai-gateway.kilo.ai/api/v1"
    guest_llm_model: str = "kilo-auto/free"
    guest_llm_api_key: str = ""  # 匿名档不校验；想带自己的 Key 就填这里
    guest_hourly_limit: int = 200  # Kilo 免费档每小时上限，游客只分一半

    # ---- Agent ----
    agent_max_steps: int = 3  # ReAct 最多思考几轮（含首轮）
    agent_memory_top_k: int = 4  # 每轮思考前召回的记忆条数
    web_search_enabled: bool = True
    tavily_api_key: str = ""  # 留空则用 DuckDuckGo HTML
    web_search_timeout: float = 12
    patrol_allow_web: bool = False  # 后台巡检默认不联网，避免定时任务频繁出网

    # ---- 托管任务 ----
    # 档位和额度已经挪到 license + access 里（本地授权文件说了算），
    # 下面两个旧字段留着只是怕老 .env 里写着，读到也不报错
    plan: str = "free"
    free_task_limit: int = 5
    pro_task_limit: int = 20
    scheduler_enabled: bool = True
    scheduler_interval: int = 20  # 子线程轮询间隔（秒，低配模式会乘 2）

    hotkey: str = "<ctrl>+<alt>+<space>"
    tray_enabled: bool = True
    window_mode: str = "webview"  # webview | browser | none
    window_width: int = 1180  # 桌面窗口，左边导航右边内容
    window_height: int = 760

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
    def log_path(self) -> Path:
        d = self.root / "logs"
        d.mkdir(parents=True, exist_ok=True)
        return d

    @property
    def env_path(self) -> Path:
        return self.root / ".env"

    @property
    def static_path(self) -> Path:
        """前端构建产物：打包时随 EXE 放在 _MEIPASS 下（onedir 里是 _internal）。"""
        if is_frozen():
            return Path(getattr(sys, "_MEIPASS", self.root)) / "frontend_dist"
        return self.root / "frontend" / "dist"


settings = Settings()
os.environ.setdefault("TQDM_DISABLE", "1")

_DEFAULT_ENV = """# StarClerk 本地配置，改完重启生效
APP_PORT=8756
LLM_PROVIDER=deepseek
LLM_BASE_URL=https://api.deepseek.com/v1
LLM_API_KEY=
LLM_MODEL=deepseek-chat
# 游客固定用的免费模型（Kilo 网关免费档，Key 可留空）
GUEST_LLM_BASE_URL=https://ai-gateway.kilo.ai/api/v1
GUEST_LLM_MODEL=kilo-auto/free
GUEST_LLM_API_KEY=
GUEST_HOURLY_LIMIT=200
EMBED_BASE_URL=http://127.0.0.1:11434/v1
EMBED_MODEL=bge-m3
EMBED_DIM=1024
HOTKEY=<ctrl>+<alt>+<space>
"""


def ensure_layout() -> None:
    """首次运行把目录和 .env 铺在 EXE 旁边，整个文件夹拷走就能换台机器用。"""
    settings.data_path
    settings.lancedb_path
    settings.upload_path
    settings.log_path
    if settings.env_path.exists():
        return
    try:
        settings.env_path.write_text(_DEFAULT_ENV, encoding="utf-8")
    except OSError:
        pass  # 目录只读就只用默认值，不影响启动
