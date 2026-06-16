import asyncio

import pytest
from fastapi.testclient import TestClient

from app.api.ws import _put_pcm_end, _put_pcm_frame
from app.main import app
from app.models.events import RevisionEvent, SourceSyncState, SubtitleSegment
from app.services.handoff import handoff_tokens
from app.services.providers.mock import build_mock_events
from app.services.session_events import session_event_hub


@pytest.fixture(autouse=True)
def reset_handoff_tokens() -> None:
    handoff_tokens.reset()
    session_event_hub.reset()


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
    assert payload["wsToken"].startswith("w_")


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
            "sourcePermission": "granted",
        },
    )

    assert response.status_code == 200
    assert response.json()["status"] == "created"


def test_mock_websocket_stream() -> None:
    client = TestClient(app)
    created = client.post("/api/sessions", json={"inputMode": "demo"}).json()
    session_id = created["sessionId"]

    with client.websocket_connect(
        f"/api/ws/sessions/{session_id}?token={created['wsToken']}"
    ) as websocket:
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


def test_mock_websocket_report_includes_emitted_segments() -> None:
    client = TestClient(app)
    created = client.post("/api/sessions", json={"inputMode": "demo"}).json()
    session_id = created["sessionId"]

    with client.websocket_connect(
        f"/api/ws/sessions/{session_id}?token={created['wsToken']}"
    ) as websocket:
        websocket.receive_json()
        websocket.send_json({"type": "start_session"})
        while True:
            event = websocket.receive_json()
            if event["type"] == "session_report":
                report_id = event["reportId"]
                break

    response = client.get(f"/api/sessions/{session_id}/report")
    assert response.status_code == 200
    report = response.json()
    assert report["reportId"] == report_id
    assert report["metrics"]["segments"] == 1
    assert report["metrics"]["realtimeRevisions"] == 1
    assert report["durationText"] == "00:04"
    segment = report["segments"][0]
    assert segment["sourceText"].startswith("Today we are going to talk")
    assert segment["finalTranslation"]


def test_mock_websocket_pause_and_resume() -> None:
    client = TestClient(app)
    created = client.post("/api/sessions", json={"inputMode": "demo"}).json()

    with client.websocket_connect(
        f"/api/ws/sessions/{created['sessionId']}?token={created['wsToken']}"
    ) as websocket:
        websocket.receive_json()

        websocket.send_json({"type": "pause_session"})
        pause_event = websocket.receive_json()
        assert pause_event["type"] == "source_sync_state"
        assert pause_event["state"]["status"] == "missing"

        websocket.send_json({"type": "resume_session"})
        resume_event = websocket.receive_json()
        assert resume_event["type"] == "source_sync_state"
        assert resume_event["state"]["status"] == "syncing"


def test_pcm_queue_drops_oldest_frame_when_full() -> None:
    queue: asyncio.Queue[bytes | None] = asyncio.Queue(maxsize=2)

    _put_pcm_frame(queue, b"a")
    _put_pcm_frame(queue, b"b")
    _put_pcm_frame(queue, b"c")

    assert [queue.get_nowait(), queue.get_nowait()] == [b"b", b"c"]


def test_pcm_queue_end_marker_replaces_oldest_frame_when_full() -> None:
    queue: asyncio.Queue[bytes | None] = asyncio.Queue(maxsize=2)

    _put_pcm_frame(queue, b"a")
    _put_pcm_frame(queue, b"b")
    _put_pcm_end(queue)

    assert [queue.get_nowait(), queue.get_nowait()] == [b"b", None]


def test_issue_and_claim_session_handoff_token_once() -> None:
    client = TestClient(app)
    response = client.post(
        "/api/sessions/desktop-session/handoff",
        json={
            "source": "system-audio",
            "sourceLanguage": "auto",
            "targetLanguage": "zh",
            "displayMode": "bilingual",
        },
    )

    assert response.status_code == 200
    issued = response.json()
    assert issued["handoffToken"].startswith("h_")
    assert issued["deepLinkUrl"].startswith("lingosync://floating/start?")
    assert "token=h_" in issued["deepLinkUrl"]

    claim_response = client.post(
        "/api/sessions/handoff/claim", json={"token": issued["handoffToken"]}
    )
    assert claim_response.status_code == 200
    claim = claim_response.json()
    assert claim["sessionId"] == "desktop-session"
    assert claim["source"] == "system-audio"
    assert claim["sourceLanguage"] == "auto"
    assert claim["targetLanguage"] == "zh"
    assert claim["displayMode"] == "bilingual"
    assert claim["wsToken"].startswith("w_")
    assert claim["wsUrl"].endswith(f"token={claim['wsToken']}")

    reused = client.post("/api/sessions/handoff/claim", json={"token": issued["handoffToken"]})
    assert reused.status_code == 409


def test_primary_websocket_requires_session_token() -> None:
    client = TestClient(app)
    created = client.post("/api/sessions", json={"inputMode": "demo"}).json()

    with client.websocket_connect(f"/api/ws/sessions/{created['sessionId']}") as websocket:
        assert websocket.receive_json() == {
            "type": "error",
            "message": "Missing WebSocket token",
        }

    with client.websocket_connect(
        f"/api/ws/sessions/{created['sessionId']}?token=bad-token"
    ) as websocket:
        assert websocket.receive_json() == {
            "type": "error",
            "message": "Invalid WebSocket token",
        }


def test_handoff_websocket_token_is_validated_for_handoff_replay() -> None:
    client = TestClient(app)
    issued = client.post("/api/sessions/ws-session/handoff", json={}).json()
    claim = client.post(
        "/api/sessions/handoff/claim", json={"token": issued["handoffToken"]}
    ).json()

    with client.websocket_connect(claim["wsUrl"]) as websocket:
        assert websocket.receive_json() == {
            "type": "session_started",
            "sessionId": "ws-session",
        }

    with client.websocket_connect("/api/ws/sessions/ws-session?token=bad-token") as websocket:
        assert websocket.receive_json() == {
            "type": "error",
            "message": "Invalid WebSocket token",
        }


def test_handoff_websocket_receives_primary_session_events() -> None:
    client = TestClient(app)
    issued = client.post("/api/sessions/mirror-session/handoff", json={}).json()
    claim = client.post(
        "/api/sessions/handoff/claim", json={"token": issued["handoffToken"]}
    ).json()
    primary_token = handoff_tokens.issue_ws_token("mirror-session", purpose="session")

    with client.websocket_connect(claim["wsUrl"]) as handoff:
        assert handoff.receive_json() == {
            "type": "session_started",
            "sessionId": "mirror-session",
        }

        with client.websocket_connect(
            f"/api/ws/sessions/mirror-session?token={primary_token}"
        ) as primary:
            primary.receive_json()
            primary.send_json({"type": "start_session"})

            primary_event = primary.receive_json()
            handoff_event = handoff.receive_json()

    assert primary_event["type"] == "source_sync_state"
    assert handoff_event == primary_event


def test_mock_events_conform_to_event_models() -> None:
    """mock 发出的 payload 必须能被事件模型校验——事件模型是前后端契约的单一事实源。"""
    events = {event["type"]: event for event in build_mock_events("contract")}

    sync_state = SourceSyncState.model_validate(events["source_sync_state"]["state"])
    assert sync_state.status in {"listening", "syncing", "lagging", "missing", "recovered"}

    SubtitleSegment.model_validate(events["transcript_segment"]["segment"])
    SubtitleSegment.model_validate(events["translation_segment"]["segment"])
    RevisionEvent.model_validate(events["revision_event"]["revision"])
