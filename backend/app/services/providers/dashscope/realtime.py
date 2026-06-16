"""LiveTranslate 实时会话 provider。

封装 qwen3.5-livetranslate-flash-realtime 的 WebSocket 协议（同一条连接完成
源语音识别 + 翻译 + 可选中文语音合成），把厂商私有事件归一化成本项目内部的
NormalizedEvent，供 services/pipeline.py 编排为统一的前后端 WS 事件。

协议要点（已实测）：
- session.update 配置语种 / 输出模态 / ASR 模型 / 热词 / 音色。
- input_audio_buffer.append 推送 base64 PCM；服务端 VAD 自动断句。
- 源识别：conversation.item.input_audio_transcription.text（流式 stash）
          → .completed（整句最终原文）。
- 翻译：response.text.text / response.audio_transcript.text（全量或增量快照）
          → response.text.done / response.audio_transcript.done（最终译文）。
- 音频模态：response.audio.delta（base64 PCM）。
- VAD：input_audio_buffer.speech_started / speech_stopped。
"""

from __future__ import annotations

import asyncio  # noqa: F401 - 供调用方在 events() 周边做超时控制
import base64
import json
import ssl
import time
from collections.abc import AsyncIterator, Callable
from dataclasses import dataclass
from typing import Any

import websockets

from .config import DashScopeConfig
from .errors import DashScopeAPIError


@dataclass
class NormalizedEvent:
    kind: str  # session_ready | speech_started | speech_stopped | source_partial
    #              | source_final | response_created | translation_partial
    #              | translation_final | audio | response_done | session_finished | error
    text: str = ""
    audio: bytes = b""
    item_id: str | None = None
    response_id: str | None = None
    raw: dict[str, Any] | None = None


class LiveTranslateSession:
    def __init__(
        self,
        config: DashScopeConfig,
        *,
        model: str,
        source_language: str = "en",
        target_language: str = "zh",
        asr_model: str = "qwen3-asr-flash-realtime",
        tts_enabled: bool = False,
        voice: str = "Cherry",
        glossary: dict[str, str] | None = None,
        websocket_connect: Callable[..., Any] | None = None,
    ) -> None:
        self.config = config
        self.model = model
        self.source_language = source_language
        self.target_language = target_language
        self.asr_model = asr_model
        self.tts_enabled = tts_enabled
        self.voice = voice
        self.glossary = glossary or {}
        self._connect = websocket_connect or websockets.connect
        self._ws: Any = None
        self._audio_transcript_by_response: dict[str, str] = {}

    # ---- 连接生命周期 ----
    async def connect(self) -> None:
        url = f"{self.config.websocket_base_url}/realtime?model={self.model}"
        kwargs: dict[str, Any] = {
            "additional_headers": self._headers(),
            "open_timeout": self.config.websocket_timeout_seconds,
            "max_size": 16 * 1024 * 1024,
        }
        if not self.config.tls_verify:
            kwargs["ssl"] = ssl._create_unverified_context()
        self._ws = await self._connect(url, **kwargs)
        await self._send(self._session_update_event())

    async def close(self) -> None:
        if self._ws is not None:
            try:
                await self._ws.close()
            except Exception:  # noqa: BLE001 - 关闭尽力而为
                pass
            self._ws = None

    async def __aenter__(self) -> LiveTranslateSession:
        await self.connect()
        return self

    async def __aexit__(self, *_exc: object) -> None:
        await self.close()

    # ---- 输入 ----
    async def feed(self, pcm: bytes) -> None:
        if self._ws is None or not pcm:
            return
        await self._send(
            {
                "type": "input_audio_buffer.append",
                "audio": base64.b64encode(pcm).decode(),
            }
        )

    async def feed_silence(self, seconds: float = 1.5, sample_rate: int = 16000) -> None:
        """补尾静音，促使 VAD 终结最后一句。"""
        await self.feed(b"\x00" * int(sample_rate * 2 * seconds))

    async def finish(self) -> None:
        """通知服务端音频输入已结束，确保最后一段被处理。"""
        if self._ws is not None:
            await self._send({"type": "session.finish"})

    # ---- 输出（归一化事件流）----
    async def events(self) -> AsyncIterator[NormalizedEvent]:
        if self._ws is None:
            raise RuntimeError("LiveTranslateSession 未连接")
        async for raw in self._ws:
            if isinstance(raw, bytes):
                continue
            message = json.loads(raw)
            event = self._normalize(message)
            if event is not None:
                yield event

    def _normalize(self, message: dict[str, Any]) -> NormalizedEvent | None:
        etype = message.get("type", "")
        item_id = message.get("item_id")
        response_id = message.get("response_id")
        if etype in ("session.created", "session.updated"):
            return NormalizedEvent(kind="session_ready", raw=message)
        if etype == "session.finished":
            return NormalizedEvent(kind="session_finished", raw=message)
        if etype == "input_audio_buffer.speech_started":
            return NormalizedEvent(kind="speech_started", item_id=item_id, raw=message)
        if etype == "input_audio_buffer.speech_stopped":
            return NormalizedEvent(kind="speech_stopped", item_id=item_id, raw=message)
        if etype == "conversation.item.input_audio_transcription.text":
            return NormalizedEvent(
                kind="source_partial",
                text=message.get("stash") or message.get("text") or "",
                item_id=item_id,
                raw=message,
            )
        if etype == "conversation.item.input_audio_transcription.completed":
            return NormalizedEvent(
                kind="source_final",
                text=message.get("transcript") or "",
                item_id=item_id,
                raw=message,
            )
        if etype == "response.created":
            rid = (message.get("response") or {}).get("id") or response_id
            return NormalizedEvent(kind="response_created", response_id=rid, raw=message)
        if etype == "response.text.text":
            # 全量快照（非增量）
            return NormalizedEvent(
                kind="translation_partial",
                text=message.get("text") or message.get("delta") or "",
                response_id=response_id,
                raw=message,
            )
        if etype in ("response.audio_transcript.text", "response.audio_transcript.delta"):
            return NormalizedEvent(
                kind="translation_partial",
                text=self._normalize_audio_transcript_partial(message, response_id),
                response_id=response_id,
                raw=message,
            )
        if etype in ("response.text.done", "response.audio_transcript.done"):
            if response_id:
                self._audio_transcript_by_response.pop(response_id, None)
            return NormalizedEvent(
                kind="translation_final",
                text=message.get("text") or message.get("transcript") or "",
                response_id=response_id,
                raw=message,
            )
        if etype == "response.audio.delta":
            return NormalizedEvent(
                kind="audio",
                audio=base64.b64decode(message.get("delta", "")),
                response_id=response_id,
                raw=message,
            )
        if etype == "response.done":
            rid = (message.get("response") or {}).get("id") or response_id
            return NormalizedEvent(kind="response_done", response_id=rid, raw=message)
        if etype == "error":
            error = message.get("error") or {}
            return NormalizedEvent(
                kind="error", text=str(error.get("message") or "LiveTranslate 错误"), raw=message
            )
        return None

    def _normalize_audio_transcript_partial(
        self, message: dict[str, Any], response_id: str | None
    ) -> str:
        value = message.get("text") or message.get("delta") or message.get("transcript") or ""
        if not value:
            return ""
        if message.get("type") == "response.audio_transcript.delta":
            return self._merge_audio_transcript_partial(response_id, str(value), delta=True)
        return self._merge_audio_transcript_partial(response_id, str(value), delta=False)

    def _merge_audio_transcript_partial(
        self, response_id: str | None, value: str, *, delta: bool
    ) -> str:
        if not response_id:
            return value
        previous = self._audio_transcript_by_response.get(response_id, "")
        if not previous:
            merged = value
        elif delta:
            merged = f"{previous}{value}"
        elif value.startswith(previous) or previous in value:
            merged = value
        elif previous.endswith(value) or value in previous:
            merged = previous
        else:
            merged = f"{previous}{value}"
        self._audio_transcript_by_response[response_id] = merged
        return merged

    # ---- 内部工具 ----
    def _session_update_event(self) -> dict[str, Any]:
        translation: dict[str, Any] = {"language": self.target_language}
        if self.glossary:
            translation["corpus"] = {"phrases": self.glossary}
        session: dict[str, Any] = {
            "modalities": ["text", "audio"] if self.tts_enabled else ["text"],
            "input_audio_format": "pcm",
            "sample_rate": 16000,
            "output_audio_format": "pcm",
            "input_audio_transcription": {
                "model": self.asr_model,
                "language": self.source_language,
            },
            "translation": translation,
        }
        if self.tts_enabled:
            session["voice"] = self._compatible_voice()
        return {"type": "session.update", "session": session}

    def _compatible_voice(self) -> str:
        if self.model.startswith("qwen3.5-livetranslate") and self.voice == "Cherry":
            return "Tina"
        return self.voice

    async def _send(self, event: dict[str, Any]) -> None:
        if self._ws is None:
            return
        event.setdefault("event_id", f"event_{int(time.time() * 1000)}")
        await self._ws.send(json.dumps(event, ensure_ascii=False))

    def _headers(self) -> dict[str, str]:
        headers = {"Authorization": f"Bearer {self.config.api_key}"}
        if self.config.workspace_id:
            headers["X-DashScope-WorkSpace"] = self.config.workspace_id
        if self.config.data_inspection:
            headers["X-DashScope-DataInspection"] = self.config.data_inspection
        return headers


def raise_if_error(event: NormalizedEvent) -> None:
    if event.kind == "error":
        raise DashScopeAPIError(event.text)
