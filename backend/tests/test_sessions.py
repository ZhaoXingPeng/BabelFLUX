from fastapi.testclient import TestClient

from app.main import app


def test_create_session() -> None:
    client = TestClient(app)
    response = client.post(
        "/api/sessions",
        json={"inputMode": "demo", "sourceLanguage": "en", "targetLanguage": "zh"},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "created"
    assert payload["sessionId"]


def test_mock_websocket_stream() -> None:
    client = TestClient(app)
    session_id = "test-session"

    with client.websocket_connect(f"/api/ws/sessions/{session_id}") as websocket:
        assert websocket.receive_json() == {
            "type": "session_started",
            "sessionId": session_id,
        }

        websocket.send_json({"type": "start_session"})
        event_types = [websocket.receive_json()["type"] for _ in range(4)]

    assert event_types == [
        "source_sync_state",
        "transcript_segment",
        "translation_segment",
        "revision_event",
    ]


def test_invalid_json_does_not_close_stream() -> None:
    client = TestClient(app)

    with client.websocket_connect("/api/ws/sessions/bad-json") as websocket:
        websocket.receive_json()  # session_started

        websocket.send_text("not-json")
        assert websocket.receive_json() == {
            "type": "error",
            "message": "Invalid JSON message",
        }

        # 单条坏帧不应中断接收循环：随后仍能正常开始一次 mock 流
        websocket.send_json({"type": "start_session"})
        event_types = [websocket.receive_json()["type"] for _ in range(4)]

    assert event_types == [
        "source_sync_state",
        "transcript_segment",
        "translation_segment",
        "revision_event",
    ]


def test_unsupported_event_returns_error() -> None:
    client = TestClient(app)

    with client.websocket_connect("/api/ws/sessions/unsupported") as websocket:
        websocket.receive_json()  # session_started
        websocket.send_json({"type": "does_not_exist"})
        assert websocket.receive_json() == {
            "type": "error",
            "message": "Unsupported client event",
        }
