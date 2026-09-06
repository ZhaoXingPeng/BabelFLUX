import httpx
import pytest
from asgi_test_client import asgi_http_client

from app.api.model_gateway import get_dashscope_client
from app.core.config import settings
from app.main import app
from app.services.providers.dashscope import ASRResult, ASRSegment, LLMResult, TTSResult


class FakeDashScopeClient:
    async def generate(self, **_: object) -> LLMResult:
        return LLMResult(
            request_id="req-1",
            model="qwen3.7-plus",
            content="成功",
            content_parts=[{"text": "成功"}],
            finish_reason="stop",
            usage={"total_tokens": 2},
        )

    async def transcribe_audio(self, *_: object, **__: object) -> ASRResult:
        return ASRResult(
            request_id="asr-1",
            model="fun-asr-realtime",
            text="hello",
            segments=[ASRSegment(text="hello", start_ms=0, end_ms=900, is_final=True)],
            events=["task-started", "result-generated", "task-finished"],
            usage={},
        )

    async def synthesize_speech(self, **_: object) -> TTSResult:
        return TTSResult(
            model="qwen3-tts-flash-realtime",
            voice="Cherry",
            audio=b"pcm-data",
            audio_format="pcm",
            sample_rate=24000,
            events=["session.created", "response.done", "session.finished"],
            session_id="session-1",
        )


async def _session_token(client: httpx.AsyncClient) -> str:
    response = await client.post("/api/sessions", json={"inputMode": "demo"})
    assert response.status_code == 200
    return str(response.json()["wsToken"])


@pytest.mark.asyncio
async def test_model_gateway_auth_rejects_missing_token_when_required() -> None:
    original = settings.require_model_gateway_auth
    object.__setattr__(settings, "require_model_gateway_auth", True)
    try:
        async with asgi_http_client() as client:
            response = await client.post(
                "/api/models/strategy/plan",
                json={"sourceLanguage": "en", "targetLanguage": "zh", "domain": "技术"},
            )
    finally:
        object.__setattr__(settings, "require_model_gateway_auth", original)

    assert response.status_code == 401


@pytest.mark.asyncio
async def test_model_gateway_auth_accepts_session_token_when_required() -> None:
    original = settings.require_model_gateway_auth
    object.__setattr__(settings, "require_model_gateway_auth", True)
    try:
        async with asgi_http_client() as client:
            token = await _session_token(client)
            response = await client.post(
                "/api/models/strategy/plan",
                headers={"Authorization": f"Bearer {token}"},
                json={"sourceLanguage": "en", "targetLanguage": "zh", "domain": "技术"},
            )
    finally:
        object.__setattr__(settings, "require_model_gateway_auth", original)

    assert response.status_code == 200


@pytest.mark.asyncio
async def test_generate_llm_api_response() -> None:
    app.dependency_overrides[get_dashscope_client] = lambda: FakeDashScopeClient()
    try:
        async with asgi_http_client() as client:
            response = await client.post(
                "/api/models/llm/generate",
                json={
                    "model": "qwen3.7-plus",
                    "endpoint": "multimodal",
                    "messages": [{"role": "user", "content": "ping"}],
                },
            )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert response.json()["content"] == "成功"
    assert response.json()["requestId"] == "req-1"


@pytest.mark.asyncio
async def test_transcribe_audio_api_response() -> None:
    app.dependency_overrides[get_dashscope_client] = lambda: FakeDashScopeClient()
    try:
        async with asgi_http_client() as client:
            response = await client.post(
                "/api/models/asr/transcriptions",
                files={"audio": ("audio.pcm", b"pcm", "application/octet-stream")},
                data={"audioFormat": "pcm", "sampleRate": "16000"},
            )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    payload = response.json()
    assert payload["text"] == "hello"
    assert payload["segments"][0]["isFinal"] is True


@pytest.mark.asyncio
async def test_synthesize_speech_api_response() -> None:
    app.dependency_overrides[get_dashscope_client] = lambda: FakeDashScopeClient()
    try:
        async with asgi_http_client() as client:
            response = await client.post("/api/models/tts/speech", json={"text": "测试成功。"})
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    payload = response.json()
    assert payload["audioBase64"] == "cGNtLWRhdGE="
    assert payload["audioBytes"] == 8
    assert payload["sampleRate"] == 24000


@pytest.mark.asyncio
async def test_strategy_plan_api_response() -> None:
    async with asgi_http_client() as client:
        response = await client.post(
            "/api/models/strategy/plan",
            json={
                "sourceLanguage": "en",
                "targetLanguage": "zh",
                "domain": "技术",
                "ttsEnabled": True,
                "glossary": [
                    {
                        "sourceTerm": "near win",
                        "targetTerm": "差一点成功",
                        "priority": 10,
                    }
                ],
            },
        )

    assert response.status_code == 200
    payload = response.json()
    assert "gummy/fun_asr provider 当前未接入真实管线" in payload["disclaimer"]
    assert payload["primaryProvider"] == "qwen_live_translate"
    assert payload["ttsProvider"] == "qwen_tts"
    assert payload["liveTranslateSession"]["event"]["session"]["modalities"] == ["text", "audio"]
    assert (
        payload["liveTranslateSession"]["event"]["session"]["translation"]["corpus"]["phrases"][
            "near win"
        ]
        == "差一点成功"
    )
    assert "finalCorrectionPrompt" in payload
