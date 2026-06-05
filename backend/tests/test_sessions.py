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
