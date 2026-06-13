from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


class APIModel(BaseModel):
    model_config = ConfigDict(populate_by_name=True)


class LLMMessage(APIModel):
    role: Literal["system", "user", "assistant"]
    content: str | list[dict[str, Any]]


class LLMGenerateRequest(APIModel):
    model: str = "qwen3.7-plus"
    endpoint: Literal["text", "multimodal"] = "multimodal"
    messages: list[LLMMessage]
    parameters: dict[str, Any] = Field(default_factory=dict)


class LLMGenerateResponse(APIModel):
    request_id: str | None = Field(default=None, alias="requestId")
    model: str
    content: str
    content_parts: list[dict[str, Any]] = Field(default_factory=list, alias="contentParts")
    finish_reason: str | None = Field(default=None, alias="finishReason")
    usage: dict[str, Any] = Field(default_factory=dict)


class ASRSegmentResponse(APIModel):
    text: str
    start_ms: int | None = Field(default=None, alias="startMs")
    end_ms: int | None = Field(default=None, alias="endMs")
    is_final: bool = Field(default=False, alias="isFinal")


class ASRTranscribeResponse(APIModel):
    request_id: str | None = Field(default=None, alias="requestId")
    model: str
    text: str
    segments: list[ASRSegmentResponse]
    events: list[str]
    usage: dict[str, Any] = Field(default_factory=dict)


class TTSSynthesizeRequest(APIModel):
    text: str
    model: str = "qwen3-tts-flash-realtime"
    voice: str = "Cherry"
    language_type: str = Field(default="Auto", alias="languageType")
    audio_format: Literal["pcm"] = Field(default="pcm", alias="audioFormat")
    sample_rate: int = Field(default=24000, alias="sampleRate")
    mode: Literal["commit", "server_commit"] = "commit"


class TTSSynthesizeResponse(APIModel):
    model: str
    voice: str
    audio_base64: str = Field(alias="audioBase64")
    audio_bytes: int = Field(alias="audioBytes")
    audio_format: str = Field(alias="audioFormat")
    sample_rate: int = Field(alias="sampleRate")
    session_id: str | None = Field(default=None, alias="sessionId")
    events: list[str]

