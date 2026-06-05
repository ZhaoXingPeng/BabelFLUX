import asyncio
import json

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from app.services.providers.mock import build_mock_events

router = APIRouter(tags=["websocket"])


@router.websocket("/ws/sessions/{session_id}")
async def session_socket(websocket: WebSocket, session_id: str) -> None:
    await websocket.accept()
    await websocket.send_json({"type": "session_started", "sessionId": session_id})

    try:
        while True:
            raw_message = await websocket.receive_text()
            message = json.loads(raw_message)

            if message.get("type") == "start_session":
                for event in build_mock_events(session_id):
                    await websocket.send_json(event)
                    await asyncio.sleep(0.25)
                continue

            if message.get("type") == "stop_session":
                await websocket.close()
                return

            await websocket.send_json({"type": "error", "message": "Unsupported client event"})
    except WebSocketDisconnect:
        return
    except json.JSONDecodeError:
        await websocket.send_json({"type": "error", "message": "Invalid JSON message"})
