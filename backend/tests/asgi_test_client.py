from __future__ import annotations

import asyncio
import contextlib
import json
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any
from urllib.parse import urlsplit

import httpx

from app.main import app


@asynccontextmanager
async def asgi_http_client() -> AsyncIterator[httpx.AsyncClient]:
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
        yield client


class ASGIWebSocketSession:
    def __init__(self, path: str, *, timeout: float = 3.0) -> None:
        self.path = path
        self.timeout = timeout
        self._client_to_app: asyncio.Queue[dict[str, Any]] = asyncio.Queue()
        self._app_to_client: asyncio.Queue[dict[str, Any]] = asyncio.Queue()
        self._task: asyncio.Task[None] | None = None
        self._closed = False

    async def __aenter__(self) -> ASGIWebSocketSession:
        split = urlsplit(self.path)
        scope = {
            "type": "websocket",
            "asgi": {"version": "3.0", "spec_version": "2.3"},
            "http_version": "1.1",
            "scheme": "ws",
            "path": split.path,
            "raw_path": split.path.encode("ascii"),
            "query_string": split.query.encode("ascii"),
            "headers": [(b"host", b"testserver")],
            "client": ("testclient", 50000),
            "server": ("testserver", 80),
            "subprotocols": [],
            "state": {},
        }
        self._task = asyncio.create_task(app(scope, self._receive, self._send))
        await self._client_to_app.put({"type": "websocket.connect"})
        accepted = await self._next_app_message()
        if accepted["type"] != "websocket.accept":
            raise AssertionError(f"Expected websocket.accept, got {accepted!r}")
        return self

    async def __aexit__(self, *_exc: object) -> None:
        await self.close()

    async def send_json(self, payload: dict[str, Any]) -> None:
        await self._client_to_app.put(
            {"type": "websocket.receive", "text": json.dumps(payload, ensure_ascii=False)}
        )

    async def receive_json(self) -> dict[str, Any]:
        while True:
            message = await self._next_app_message()
            if message["type"] == "websocket.send":
                text = message.get("text")
                if text is None:
                    data = message.get("bytes") or b""
                    text = data.decode("utf-8")
                return json.loads(text)
            if message["type"] == "websocket.close":
                self._closed = True
                raise AssertionError(f"WebSocket closed before JSON message: {message!r}")

    async def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        await self._client_to_app.put({"type": "websocket.disconnect", "code": 1000})
        if self._task is not None:
            try:
                await asyncio.wait_for(self._task, timeout=self.timeout)
            except TimeoutError:
                self._task.cancel()
                with contextlib.suppress(asyncio.CancelledError):
                    await self._task

    async def _receive(self) -> dict[str, Any]:
        return await self._client_to_app.get()

    async def _send(self, message: dict[str, Any]) -> None:
        await self._app_to_client.put(message)

    async def _next_app_message(self) -> dict[str, Any]:
        return await asyncio.wait_for(self._app_to_client.get(), timeout=self.timeout)
