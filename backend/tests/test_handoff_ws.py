import asyncio
import json

import pytest

from app.api.handoff_ws import serve_handoff_socket
from app.services.session_events import session_event_hub


class FakeWebSocket:
    def __init__(self, messages: list[dict[str, str]]) -> None:
        self.messages = iter(messages)
        self.sent: list[dict[str, object]] = []

    async def send_json(self, payload: dict[str, object]) -> None:
        self.sent.append(payload)

    async def receive(self) -> dict[str, str]:
        await asyncio.sleep(0)
        return next(self.messages)


@pytest.mark.asyncio
async def test_handoff_socket_replays_events_and_unsubscribes_on_stop() -> None:
    session_event_hub.publish("handoff-test", {"type": "translation_segment", "segmentId": "s1"})
    websocket = FakeWebSocket([{"text": json.dumps({"type": "stop_session"})}])

    await serve_handoff_socket(websocket, "handoff-test")

    assert websocket.sent == [
        {"type": "session_started", "sessionId": "handoff-test"},
        {"type": "translation_segment", "segmentId": "s1"},
    ]
    assert not session_event_hub._subscribers.get("handoff-test")


@pytest.mark.asyncio
async def test_handoff_socket_reports_invalid_json_and_cleans_up_on_disconnect() -> None:
    websocket = FakeWebSocket([
        {"text": "{"},
        {"type": "websocket.disconnect"},
    ])

    await serve_handoff_socket(websocket, "handoff-error")

    assert websocket.sent == [
        {"type": "session_started", "sessionId": "handoff-error"},
        {"type": "error", "message": "Invalid JSON message"},
    ]
    assert not session_event_hub._subscribers.get("handoff-error")
