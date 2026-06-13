from dataclasses import dataclass, field

from app.core.config import Settings

from .errors import DashScopeConfigurationError


@dataclass(frozen=True)
class DashScopeConfig:
    api_key: str = field(repr=False)
    workspace_id: str | None = None
    http_base_url: str = "https://dashscope.aliyuncs.com/api/v1"
    websocket_base_url: str = "wss://dashscope.aliyuncs.com/api-ws/v1"
    request_timeout_seconds: float = 30.0
    websocket_timeout_seconds: float = 30.0
    tls_verify: bool = True
    data_inspection: str | None = None

    @classmethod
    def from_settings(cls, settings: Settings) -> "DashScopeConfig":
        if not settings.dashscope_api_key:
            raise DashScopeConfigurationError("DASHSCOPE_API_KEY is required")

        return cls(
            api_key=settings.dashscope_api_key,
            workspace_id=settings.dashscope_workspace_id,
            http_base_url=settings.dashscope_http_base_url.rstrip("/"),
            websocket_base_url=settings.dashscope_websocket_base_url.rstrip("/"),
            request_timeout_seconds=settings.dashscope_request_timeout_seconds,
            websocket_timeout_seconds=settings.dashscope_websocket_timeout_seconds,
            tls_verify=settings.dashscope_tls_verify,
            data_inspection=settings.dashscope_data_inspection,
        )

    def text_generation_url(self) -> str:
        return f"{self.http_base_url}/services/aigc/text-generation/generation"

    def multimodal_generation_url(self) -> str:
        return f"{self.http_base_url}/services/aigc/multimodal-generation/generation"

    def asr_websocket_url(self) -> str:
        return f"{self.websocket_base_url}/inference"

    def tts_realtime_websocket_url(self, model: str) -> str:
        return f"{self.websocket_base_url}/realtime?model={model}"

