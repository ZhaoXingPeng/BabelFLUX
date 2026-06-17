import base64
import json
from typing import Any

import httpx
import pytest

from app.core.config import Settings
from app.services.providers.dashscope import (
    ASRSegment,
    DashScopeClient,
    DashScopeConfig,
    LiveTranslateSession,
)
from app.services.providers.dashscope.errors import DashScopeConfigurationError


class FakeWebSocket:
    def __init__(self, messages: list[dict[str, Any]]) -> None:
        self.messages = [json.dumps(message) for message in messages]
        self.sent: list[str | bytes] = []

    async def __aenter__(self) -> "FakeWebSocket":
        return self

    async def __aexit__(self, *_: object) -> None:
        return None

    async def send(self, message: str | bytes) -> None:
        self.sent.append(message)

    async def recv(self) -> str:
        if not self.messages:
            raise AssertionError("no fake websocket messages left")
        return self.messages.pop(0)


class FakeWebSocketConnector:
    def __init__(self, websocket: FakeWebSocket) -> None:
        self.websocket = websocket
        self.url: str | None = None
        self.kwargs: dict[str, Any] = {}

    def __call__(self, url: str, **kwargs: Any) -> FakeWebSocket:
        self.url = url
        self.kwargs = kwargs
        return self.websocket


def test_dashscope_config_requires_api_key() -> None:
    settings = Settings(dashscope_api_key=None)

    with pytest.raises(DashScopeConfigurationError):
        DashScopeConfig.from_settings(settings)


def test_live_translate_session_update_declares_low_latency_pcm_rate() -> None:
    session = LiveTranslateSession(DashScopeConfig(api_key="test-key"), model="m")

    event = session._session_update_event()

    assert event["session"]["input_audio_format"] == "pcm"
    assert event["session"]["sample_rate"] == 16000
    assert event["session"]["output_audio_format"] == "pcm"


def test_live_translate_session_update_can_request_auto_source_language() -> None:
    session = LiveTranslateSession(
        DashScopeConfig(api_key="test-key"),
        model="m",
        source_language="auto",
        target_language="zh",
    )

    event = session._session_update_event()

    assert event["session"]["input_audio_transcription"]["language"] == "auto"
    assert event["session"]["translation"]["language"] == "zh"


def test_live_translate_qwen35_tts_uses_supported_voice_for_legacy_cherry() -> None:
    session = LiveTranslateSession(
        DashScopeConfig(api_key="test-key"),
        model="qwen3.5-livetranslate-flash-realtime",
        tts_enabled=True,
        voice="Cherry",
    )

    event = session._session_update_event()

    assert event["session"]["modalities"] == ["text", "audio"]
    assert event["session"]["voice"] == "Tina"


def test_live_translate_normalizes_audio_transcript_partials() -> None:
    session = LiveTranslateSession(DashScopeConfig(api_key="test-key"), model="m")

    first = session._normalize(
        {
            "type": "response.audio_transcript.delta",
            "response_id": "resp-1",
            "delta": "你好",
        }
    )
    second = session._normalize(
        {
            "type": "response.audio_transcript.delta",
            "response_id": "resp-1",
            "delta": "世界",
        }
    )
    final = session._normalize(
        {
            "type": "response.audio_transcript.done",
            "response_id": "resp-1",
            "transcript": "你好世界",
        }
    )
    finished = session._normalize({"type": "session.finished"})

    assert first is not None
    assert first.kind == "translation_partial"
    assert first.text == "你好"
    assert second is not None
    assert second.kind == "translation_partial"
    assert second.text == "你好世界"
    assert final is not None
    assert final.kind == "translation_final"
    assert final.text == "你好世界"
    assert finished is not None
    assert finished.kind == "session_finished"


def test_live_translate_audio_transcript_text_partials_replace_snapshots() -> None:
    session = LiveTranslateSession(DashScopeConfig(api_key="test-key"), model="m")

    first = session._normalize(
        {
            "type": "response.audio_transcript.text",
            "response_id": "resp-1",
            "text": "你好",
        }
    )
    second = session._normalize(
        {
            "type": "response.audio_transcript.text",
            "response_id": "resp-1",
            "text": "你好世界",
        }
    )

    assert first is not None
    assert first.text == "你好"
    assert second is not None
    assert second.text == "你好世界"


@pytest.mark.asyncio
async def test_live_translate_finish_sends_session_finish_event() -> None:
    websocket = FakeWebSocket([])

    async def connect(_url: str, **_kwargs: Any) -> FakeWebSocket:
        return websocket

    session = LiveTranslateSession(
        DashScopeConfig(api_key="test-key", workspace_id="workspace-1"),
        model="qwen3.5-livetranslate-flash-realtime",
        websocket_connect=connect,
    )

    await session.connect()
    await session.finish()

    sent_events = [
        json.loads(message)["type"] for message in websocket.sent if isinstance(message, str)
    ]
    assert sent_events == ["session.update", "session.finish"]


@pytest.mark.asyncio
async def test_llm_multimodal_request_and_response_are_normalized() -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        assert request.url.path == "/api/v1/services/aigc/multimodal-generation/generation"
        assert request.headers["authorization"] == "Bearer test-key"
        assert request.headers["x-dashscope-workspace"] == "workspace-1"
        assert body["model"] == "qwen3.7-plus"
        assert body["input"]["messages"][0]["content"] == [{"text": "ping"}]
        return httpx.Response(
            200,
            json={
                "request_id": "req-1",
                "output": {
                    "choices": [
                        {
                            "finish_reason": "stop",
                            "message": {"content": [{"text": "pong"}]},
                        }
                    ]
                },
                "usage": {"total_tokens": 2},
            },
        )

    async with httpx.AsyncClient(
        transport=httpx.MockTransport(handler),
        base_url="https://dashscope.aliyuncs.com",
    ) as http_client:
        client = DashScopeClient(
            DashScopeConfig(
                api_key="test-key",
                workspace_id="workspace-1",
                http_base_url="https://dashscope.aliyuncs.com/api/v1",
            ),
            http_client=http_client,
        )
        result = await client.generate(
            model="qwen3.7-plus",
            endpoint="multimodal",
            messages=[{"role": "user", "content": "ping"}],
        )

    assert result.request_id == "req-1"
    assert result.content == "pong"
    assert result.content_parts == [{"text": "pong"}]
    assert result.usage == {"total_tokens": 2}


@pytest.mark.asyncio
async def test_asr_websocket_flow_collects_segments() -> None:
    websocket = FakeWebSocket(
        [
            {"header": {"event": "task-started", "request_id": "asr-1"}},
            {
                "header": {"event": "result-generated"},
                "payload": {
                    "output": {
                        "sentence": {
                            "text": "hello",
                            "begin_time": 0,
                            "end_time": 900,
                            "sentence_end": True,
                        }
                    }
                },
            },
            {"header": {"event": "task-finished"}, "payload": {"usage": {"duration": 1}}},
        ]
    )
    connector = FakeWebSocketConnector(websocket)
    client = DashScopeClient(
        DashScopeConfig(api_key="test-key", workspace_id="workspace-1"),
        websocket_connect=connector,
    )

    result = await client.transcribe_audio(
        b"0" * 6400,
        model="fun-asr-realtime",
        chunk_interval_seconds=0,
    )

    assert connector.url == "wss://dashscope.aliyuncs.com/api-ws/v1/inference"
    assert connector.kwargs["additional_headers"]["Authorization"] == "Bearer test-key"
    assert result.text == "hello"
    assert result.segments == [ASRSegment(text="hello", start_ms=0, end_ms=900, is_final=True)]
    assert result.events == ["task-started", "result-generated", "task-finished"]
    assert any(isinstance(message, bytes) for message in websocket.sent)


@pytest.mark.asyncio
async def test_tts_realtime_flow_collects_audio() -> None:
    audio_chunk = b"pcm-data"
    websocket = FakeWebSocket(
        [
            {"type": "session.created", "session": {"id": "session-1"}},
            {"type": "session.updated", "session": {"id": "session-1"}},
            {"type": "input_text_buffer.committed"},
            {"type": "response.created"},
            {
                "type": "response.audio.delta",
                "delta": base64.b64encode(audio_chunk).decode("ascii"),
            },
            {"type": "response.done"},
            {"type": "session.finished"},
        ]
    )
    connector = FakeWebSocketConnector(websocket)
    client = DashScopeClient(
        DashScopeConfig(api_key="test-key", workspace_id="workspace-1"),
        websocket_connect=connector,
    )

    result = await client.synthesize_speech(text="测试", voice="Cherry")

    assert connector.url == (
        "wss://dashscope.aliyuncs.com/api-ws/v1/realtime?model=qwen3-tts-flash-realtime"
    )
    assert result.audio == audio_chunk
    assert result.session_id == "session-1"
    sent_events = [
        json.loads(message)["type"] for message in websocket.sent if isinstance(message, str)
    ]
    assert sent_events == [
        "session.update",
        "input_text_buffer.append",
        "input_text_buffer.commit",
        "session.finish",
    ]
