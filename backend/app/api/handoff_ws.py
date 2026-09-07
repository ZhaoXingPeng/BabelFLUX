"""handoff WebSocket 的只读事件转发适配器。"""

from __future__ import annotations

import asyncio
import json
from contextlib import suppress

from fastapi import WebSocket, WebSocketDisconnect

from app.services.session_commands import parse_client_payload
from app.services.session_events import session_event_hub


async def serve_handoff_socket(websocket: WebSocket, session_id: str) -> None:
    """把主会话事件回放并转发给 handoff 客户端，不启动第二条管线。"""
    subscription = session_event_hub.subscribe(session_id)
    await websocket.send_json({"type": "session_started", "sessionId": session_id})

    for event in subscription.replay:
        await websocket.send_json(event)

    async def forward_events() -> None:
        while True:
            await websocket.send_json(await subscription.queue.get())

    forward_task = asyncio.create_task(forward_events())
    try:
        while True:
            message = await websocket.receive()
            if message.get("type") == "websocket.disconnect":
                break
            text = message.get("text")
            if not text:
                continue
            try:
                payload, error_message = parse_client_payload(text)
            except json.JSONDecodeError:
                await websocket.send_json({"type": "error", "message": "Invalid JSON message"})
                continue
            if error_message:
                await websocket.send_json({"type": "error", "message": error_message})
                continue
            assert payload is not None
            if payload.get("type") == "stop_session":
                break
    except WebSocketDisconnect:
        pass
    finally:
        session_event_hub.unsubscribe(subscription)
        forward_task.cancel()
        with suppress(asyncio.CancelledError):
            await forward_task
