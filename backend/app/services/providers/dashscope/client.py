import asyncio
import base64
import json
import ssl
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any, Literal
from uuid import uuid4

import httpx
import websockets

from .config import DashScopeConfig
from .errors import DashScopeAPIError

GenerationEndpoint = Literal["text", "multimodal"]


@dataclass(frozen=True)
class LLMResult:
    request_id: str | None
    model: str
    content: str
    content_parts: list[dict[str, Any]]
    finish_reason: str | None
    usage: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class ASRSegment:
    text: str
    start_ms: int | None = None
    end_ms: int | None = None
    is_final: bool = False


@dataclass(frozen=True)
class ASRResult:
    request_id: str | None
    model: str
    text: str
    segments: list[ASRSegment]
    events: list[str]
    usage: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class TTSResult:
    model: str
    voice: str
    audio: bytes
    audio_format: str
    sample_rate: int
    events: list[str]
    session_id: str | None = None


class DashScopeClient:
    def __init__(
        self,
        config: DashScopeConfig,
        *,
        http_client: httpx.AsyncClient | None = None,
        websocket_connect: Callable[..., Any] | None = None,
    ) -> None:
        self.config = config
        self._http_client = http_client
        self._websocket_connect = websocket_connect or websockets.connect

    async def generate(
        self,
        *,
        model: str,
        messages: list[dict[str, Any]],
        endpoint: GenerationEndpoint,
        parameters: dict[str, Any] | None = None,
    ) -> LLMResult:
        payload = {
            "model": model,
            "input": {"messages": self._generation_messages(messages, endpoint)},
            "parameters": parameters or {},
        }
        if endpoint == "text":
            payload["parameters"] = {"result_format": "message", **payload["parameters"]}
            url = self.config.text_generation_url()
        else:
            url = self.config.multimodal_generation_url()

        data = await self._post_json(url, payload)
        output = data.get("output") or {}
        choices = output.get("choices") or []
        choice = choices[0] if choices else {}
        message = choice.get("message") or {}
        content, content_parts = self._extract_generation_content(message, output)

        return LLMResult(
            request_id=data.get("request_id") or data.get("requestId"),
            model=model,
            content=content,
            content_parts=content_parts,
            finish_reason=choice.get("finish_reason") or output.get("finish_reason"),
            usage=data.get("usage") or {},
        )

    async def transcribe_audio(
        self,
        audio: bytes,
        *,
        model: str = "fun-asr-realtime",
        audio_format: str = "pcm",
        sample_rate: int = 16000,
        chunk_size: int = 3200,
        chunk_interval_seconds: float = 0.03,
    ) -> ASRResult:
        task_id = str(uuid4())
        events: list[str] = []
        segments: list[ASRSegment] = []
        request_id: str | None = None
        usage: dict[str, Any] = {}

        async with self._connect_websocket(self.config.asr_websocket_url()) as ws:
            await ws.send(
                json.dumps(
                    {
                        "header": {
                            "action": "run-task",
                            "task_id": task_id,
                            "streaming": "duplex",
                        },
                        "payload": {
                            "task_group": "audio",
                            "task": "asr",
                            "function": "recognition",
                            "model": model,
                            "parameters": {
                                "format": audio_format,
                                "sample_rate": sample_rate,
                            },
                            "input": {},
                        },
                    },
                    ensure_ascii=False,
                )
            )
            await self._wait_for_event(ws, "task-started", events)

            for offset in range(0, len(audio), chunk_size):
                await ws.send(audio[offset : offset + chunk_size])
                if chunk_interval_seconds > 0:
                    await asyncio.sleep(chunk_interval_seconds)

            await ws.send(
                json.dumps(
                    {
                        "header": {
                            "action": "finish-task",
                            "task_id": task_id,
                            "streaming": "duplex",
                        },
                        "payload": {"input": {}},
                    },
                    ensure_ascii=False,
                )
            )

            while True:
                message = await self._recv_json(ws)
                event = self._event_name(message)
                events.append(event)
                request_id = request_id or self._request_id(message)

                if event == "result-generated":
                    segment = self._asr_segment(message)
                    if segment:
                        segments.append(segment)
                    continue
                if event == "task-finished":
                    usage = (message.get("payload") or {}).get("usage") or {}
                    break
                if event == "task-failed":
                    self._raise_ws_error(message)

        final_segments = [segment.text for segment in segments if segment.is_final]
        text = (
            " ".join(final_segments)
            if final_segments
            else (segments[-1].text if segments else "")
        )
        return ASRResult(
            request_id=request_id,
            model=model,
            text=text,
            segments=segments,
            events=events,
            usage=usage,
        )

    async def synthesize_speech(
        self,
        *,
        text: str,
        model: str = "qwen3-tts-flash-realtime",
        voice: str = "Cherry",
        language_type: str = "Auto",
        audio_format: str = "pcm",
        sample_rate: int = 24000,
        mode: Literal["commit", "server_commit"] = "commit",
    ) -> TTSResult:
        events: list[str] = []
        audio = bytearray()
        session_id: str | None = None

        async with self._connect_websocket(self.config.tts_realtime_websocket_url(model)) as ws:
            await self._send_realtime_event(
                ws,
                {
                    "type": "session.update",
                    "session": {
                        "mode": mode,
                        "voice": voice,
                        "language_type": language_type,
                        "response_format": audio_format,
                        "sample_rate": sample_rate,
                    },
                },
            )
            while True:
                message = await self._recv_json(ws)
                event = message.get("type", "")
                events.append(event)
                if event == "session.created":
                    session_id = (message.get("session") or {}).get("id")
                    continue
                if event == "session.updated":
                    session_id = session_id or (message.get("session") or {}).get("id")
                    break
                if event == "error":
                    self._raise_realtime_error(message)

            await self._send_realtime_event(ws, {"type": "input_text_buffer.append", "text": text})
            if mode == "commit":
                await self._send_realtime_event(ws, {"type": "input_text_buffer.commit"})

            while True:
                message = await self._recv_json(ws)
                event = message.get("type", "")
                events.append(event)
                if event == "response.audio.delta":
                    audio.extend(base64.b64decode(message.get("delta", "")))
                    continue
                if event == "response.done":
                    break
                if event == "error":
                    self._raise_realtime_error(message)

            await self._send_realtime_event(ws, {"type": "session.finish"})
            while True:
                message = await self._recv_json(ws)
                event = message.get("type", "")
                events.append(event)
                if event == "session.finished":
                    break
                if event == "error":
                    self._raise_realtime_error(message)

        return TTSResult(
            model=model,
            voice=voice,
            audio=bytes(audio),
            audio_format=audio_format,
            sample_rate=sample_rate,
            events=events,
            session_id=session_id,
        )

    async def _post_json(self, url: str, payload: dict[str, Any]) -> dict[str, Any]:
        if self._http_client:
            response = await self._http_client.post(url, headers=self._headers(), json=payload)
        else:
            timeout = httpx.Timeout(self.config.request_timeout_seconds)
            async with httpx.AsyncClient(timeout=timeout, verify=self.config.tls_verify) as client:
                response = await client.post(url, headers=self._headers(), json=payload)

        try:
            data = response.json()
        except ValueError as exc:
            raise DashScopeAPIError(
                "DashScope returned a non-JSON response",
                status_code=response.status_code,
            ) from exc

        if response.status_code >= 400:
            raise DashScopeAPIError(
                str(data.get("message") or "DashScope request failed"),
                status_code=response.status_code,
                code=data.get("code"),
                request_id=data.get("request_id") or data.get("requestId"),
            )
        return data

    def _connect_websocket(self, url: str) -> Any:
        kwargs: dict[str, Any] = {
            "additional_headers": self._headers(),
            "open_timeout": self.config.websocket_timeout_seconds,
            "max_size": 8 * 1024 * 1024,
        }
        if not self.config.tls_verify:
            kwargs["ssl"] = ssl._create_unverified_context()
        return self._websocket_connect(url, **kwargs)

    def _headers(self) -> dict[str, str]:
        headers = {"Authorization": f"Bearer {self.config.api_key}"}
        if self.config.workspace_id:
            headers["X-DashScope-WorkSpace"] = self.config.workspace_id
        if self.config.data_inspection:
            headers["X-DashScope-DataInspection"] = self.config.data_inspection
        return headers

    async def _wait_for_event(self, ws: Any, expected_event: str, events: list[str]) -> None:
        while True:
            message = await self._recv_json(ws)
            event = self._event_name(message)
            events.append(event)
            if event == expected_event:
                return
            if event == "task-failed":
                self._raise_ws_error(message)

    async def _recv_json(self, ws: Any) -> dict[str, Any]:
        raw_message = await asyncio.wait_for(
            ws.recv(),
            timeout=self.config.websocket_timeout_seconds,
        )
        if isinstance(raw_message, bytes):
            return {}
        return json.loads(raw_message)

    async def _send_realtime_event(self, ws: Any, event: dict[str, Any]) -> None:
        event["event_id"] = f"event_{int(time.time() * 1000)}"
        await ws.send(json.dumps(event, ensure_ascii=False))

    def _generation_messages(
        self,
        messages: list[dict[str, Any]],
        endpoint: GenerationEndpoint,
    ) -> list[dict[str, Any]]:
        if endpoint == "text":
            return messages

        multimodal_messages = []
        for message in messages:
            item = dict(message)
            content = item.get("content")
            if isinstance(content, str):
                item["content"] = [{"text": content}]
            multimodal_messages.append(item)
        return multimodal_messages

    def _extract_generation_content(
        self,
        message: dict[str, Any],
        output: dict[str, Any],
    ) -> tuple[str, list[dict[str, Any]]]:
        content = message.get("content") or output.get("text") or ""
        if isinstance(content, str):
            return content, [{"text": content}] if content else []
        if isinstance(content, list):
            texts = [str(part.get("text", "")) for part in content if isinstance(part, dict)]
            return "".join(texts), [part for part in content if isinstance(part, dict)]
        return str(content), []

    def _asr_segment(self, message: dict[str, Any]) -> ASRSegment | None:
        sentence = ((message.get("payload") or {}).get("output") or {}).get("sentence") or {}
        text = sentence.get("text")
        if not text:
            return None
        return ASRSegment(
            text=text,
            start_ms=sentence.get("begin_time"),
            end_ms=sentence.get("end_time"),
            is_final=bool(sentence.get("sentence_end")),
        )

    def _event_name(self, message: dict[str, Any]) -> str:
        return str((message.get("header") or {}).get("event") or "")

    def _request_id(self, message: dict[str, Any]) -> str | None:
        return (message.get("header") or {}).get("request_id") or (
            message.get("header") or {}
        ).get("requestId")

    def _raise_ws_error(self, message: dict[str, Any]) -> None:
        header = message.get("header") or {}
        raise DashScopeAPIError(
            str(header.get("error_message") or "DashScope WebSocket task failed"),
            code=header.get("error_code"),
            request_id=header.get("request_id") or header.get("requestId"),
        )

    def _raise_realtime_error(self, message: dict[str, Any]) -> None:
        error = message.get("error") or {}
        raise DashScopeAPIError(
            str(error.get("message") or "DashScope realtime request failed"),
            code=error.get("code"),
            request_id=message.get("event_id"),
        )
