from functools import lru_cache
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

PROJECT_ROOT = Path(__file__).resolve().parents[3]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=PROJECT_ROOT / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    app_name: str = "BabelFlux Backend"
    api_prefix: str = "/api"
    app_env: str = "development"
    frontend_origin: str = "http://localhost:5173"
    database_url: str = "sqlite:///./data/app.db"
    # real = 接入阿里云百炼实时管线；mock = 纯演示事件流。
    model_provider: str = "mock"
    dashscope_api_key: str | None = Field(default=None, repr=False)
    dashscope_workspace_id: str | None = None
    dashscope_http_base_url: str = "https://dashscope.aliyuncs.com/api/v1"
    dashscope_websocket_base_url: str = "wss://dashscope.aliyuncs.com/api-ws/v1"
    dashscope_request_timeout_seconds: float = 60.0
    dashscope_websocket_timeout_seconds: float = 60.0
    dashscope_tls_verify: bool = True
    dashscope_data_inspection: str | None = None

    # ===== 模型选型（已实测可用，见 docs/model-pipeline）=====
    live_translate_model: str = "qwen3.5-livetranslate-flash-realtime"
    live_translate_asr_model: str = "qwen3-asr-flash-realtime"
    realtime_revision_model: str = "qwen-flash"
    final_correction_model: str = "qwen-plus"
    final_correction_timeout_seconds: float = 8.0
    tts_model: str = "qwen3-tts-flash-realtime"
    tts_voice: str = "Cherry"

    # demo 模式下若指向存在的媒体文件，则用真实管线跑该样例；为空则回退到演示事件流。
    demo_media_path: str = ""

    # 运行期产物目录（上传媒体、生成报告）。相对 PROJECT_ROOT。
    media_storage_dir: str = "backend/data/media"
    report_storage_dir: str = "backend/data/reports"

    @property
    def media_dir(self) -> Path:
        path = (PROJECT_ROOT / self.media_storage_dir).resolve()
        path.mkdir(parents=True, exist_ok=True)
        return path

    @property
    def report_dir(self) -> Path:
        path = (PROJECT_ROOT / self.report_storage_dir).resolve()
        path.mkdir(parents=True, exist_ok=True)
        return path

    @property
    def use_real_pipeline(self) -> bool:
        return self.model_provider == "real" and bool(self.dashscope_api_key)

    @property
    def cors_origins(self) -> list[str]:
        # 同时放行 localhost 与 127.0.0.1 两种本地访问形式（Vite 绑定 0.0.0.0，两者都可能用到）
        origins = {self.frontend_origin}
        if "localhost" in self.frontend_origin:
            origins.add(self.frontend_origin.replace("localhost", "127.0.0.1"))
        elif "127.0.0.1" in self.frontend_origin:
            origins.add(self.frontend_origin.replace("127.0.0.1", "localhost"))
        origins.update(
            {
                "http://localhost:5175",
                "http://127.0.0.1:5175",
                "http://tauri.localhost",
                "tauri://localhost",
            }
        )
        return sorted(origins)


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
