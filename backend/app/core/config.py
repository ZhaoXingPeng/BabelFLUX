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

    @property
    def cors_origins(self) -> list[str]:
        return [self.frontend_origin]


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
