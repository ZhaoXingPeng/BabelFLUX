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

    app_name: str = "AI Product Lab Backend"
    api_prefix: str = "/api"
    app_env: str = "development"
    frontend_origin: str = "http://localhost:5173"
    database_url: str = "sqlite:///./data/app.db"
    model_provider: str = "mock"
    dashscope_api_key: str | None = Field(default=None, repr=False)
    dashscope_workspace_id: str | None = None
    dashscope_http_base_url: str = "https://dashscope.aliyuncs.com/api/v1"
    dashscope_websocket_base_url: str = "wss://dashscope.aliyuncs.com/api-ws/v1"
    dashscope_request_timeout_seconds: float = 30.0
    dashscope_websocket_timeout_seconds: float = 30.0
    dashscope_tls_verify: bool = True
    dashscope_data_inspection: str | None = None

    @property
    def cors_origins(self) -> list[str]:
        # 同时放行 localhost 与 127.0.0.1 两种本地访问形式（Vite 绑定 0.0.0.0，两者都可能用到）
        origins = {self.frontend_origin}
        if "localhost" in self.frontend_origin:
            origins.add(self.frontend_origin.replace("localhost", "127.0.0.1"))
        elif "127.0.0.1" in self.frontend_origin:
            origins.add(self.frontend_origin.replace("127.0.0.1", "localhost"))
        return sorted(origins)


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
