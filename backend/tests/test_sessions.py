from fastapi.testclient import TestClient

from app.main import app
from app.models.events import RevisionEvent, SourceSyncState, SubtitleSegment
from app.services.providers.mock import build_mock_events


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


def test_create_session_accepts_configured_frontend_payload() -> None:
    client = TestClient(app)
    response = client.post(
        "/api/sessions",
        json={
            "inputMode": "browser_audio",
            "sourceLanguage": "en",
            "targetLanguage": "ja",
            "productMode": "quick",
            "sessionName": "季度发布会同传",
            "domain": "商务",
            "modelProfile": "高准确",
            "sourceKey": "browser-tab",
        },
    )

    assert response.status_code == 200
    assert response.json()["status"] == "created"


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


def test_mock_websocket_pause_and_resume() -> None:
    client = TestClient(app)

    with client.websocket_connect("/api/ws/sessions/test-session") as websocket:
        websocket.receive_json()

        websocket.send_json({"type": "pause_session"})
        pause_event = websocket.receive_json()
        assert pause_event["type"] == "source_sync_state"
        assert pause_event["state"]["status"] == "missing"

        websocket.send_json({"type": "resume_session"})
        resume_event = websocket.receive_json()
        assert resume_event["type"] == "source_sync_state"
        assert resume_event["state"]["status"] == "syncing"


def test_mock_events_conform_to_event_models() -> None:
    """mock 发出的 payload 必须能被事件模型校验——事件模型是前后端契约的单一事实源。"""
    events = {event["type"]: event for event in build_mock_events("contract")}

    sync_state = SourceSyncState.model_validate(events["source_sync_state"]["state"])
    assert sync_state.status in {"listening", "syncing", "lagging", "missing", "recovered"}

    SubtitleSegment.model_validate(events["transcript_segment"]["segment"])
    SubtitleSegment.model_validate(events["translation_segment"]["segment"])
    RevisionEvent.model_validate(events["revision_event"]["revision"])
