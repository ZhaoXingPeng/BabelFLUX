from fastapi.testclient import TestClient

from app.api.model_gateway import get_dashscope_client
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


def test_generate_llm_api_response() -> None:
    app.dependency_overrides[get_dashscope_client] = lambda: FakeDashScopeClient()
    try:
        client = TestClient(app)
        response = client.post(
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


def test_transcribe_audio_api_response() -> None:
    app.dependency_overrides[get_dashscope_client] = lambda: FakeDashScopeClient()
    try:
        client = TestClient(app)
        response = client.post(
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


def test_synthesize_speech_api_response() -> None:
    app.dependency_overrides[get_dashscope_client] = lambda: FakeDashScopeClient()
    try:
        client = TestClient(app)
        response = client.post("/api/models/tts/speech", json={"text": "测试成功。"})
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    payload = response.json()
    assert payload["audioBase64"] == "cGNtLWRhdGE="
    assert payload["audioBytes"] == 8
    assert payload["sampleRate"] == 24000

