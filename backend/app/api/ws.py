import asyncio
import json

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from app.services.providers.mock import build_mock_events
from app.services.handoff import handoff_tokens

router = APIRouter(tags=["websocket"])


@router.websocket("/ws/sessions/{session_id}")
async def session_socket(websocket: WebSocket, session_id: str) -> None:
    await websocket.accept()
    ws_token = websocket.query_params.get("token")
    if ws_token and not handoff_tokens.validate_ws_token(session_id, ws_token):
        await websocket.send_json({"type": "error", "message": "Invalid handoff WebSocket token"})
        await websocket.close(code=4401)
        return

    await websocket.send_json({"type": "session_started", "sessionId": session_id})

    try:
        while True:
            raw_message = await websocket.receive_text()

            try:
                message = json.loads(raw_message)
            except json.JSONDecodeError:
                await websocket.send_json({"type": "error", "message": "Invalid JSON message"})
                continue

            message_type = message.get("type")

            if message_type == "start_session":
                for event in build_mock_events(session_id):
                    await websocket.send_json(event)
                    await asyncio.sleep(0.25)
                continue

            if message_type == "pause_session":
                await websocket.send_json(
                    {
                        "type": "source_sync_state",
                        "state": {
                            "status": "missing",
                            "lagMs": 0,
                            "message": "会话已暂停",
                        },
                    }
                )
                continue

            if message_type == "resume_session":
                await websocket.send_json(
                    {
                        "type": "source_sync_state",
                        "state": {
                            "status": "syncing",
                            "lagMs": 160,
                            "message": "会话已继续",
                        },
                    }
                )
                continue

            if message_type == "stop_session":
                await websocket.close()
                return

            await websocket.send_json({"type": "error", "message": "Unsupported client event"})
    except WebSocketDisconnect:
        return
