import asyncio
import json

import pytest
from asgi_test_client import ASGIWebSocketSession, asgi_http_client

from app.api.ws import _put_pcm_end, _put_pcm_frame
from app.core.config import settings
from app.models.events import RevisionEvent, SourceSyncState, SubtitleSegment
from app.services.handoff import handoff_tokens
from app.services.providers.mock import build_mock_events
from app.services.session_events import session_event_hub
from app.services.session_history import session_history_store
from app.services.session_store import session_store


@pytest.fixture(autouse=True)
def reset_handoff_tokens() -> None:
    handoff_tokens.reset()
    session_event_hub.reset()


@pytest.mark.asyncio
async def test_create_session() -> None:
    async with asgi_http_client() as client:
        response = await client.post(
            "/api/sessions",
            json={"inputMode": "demo", "sourceLanguage": "en", "targetLanguage": "zh"},
        )

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "created"
    assert payload["sessionId"]
    assert payload["wsToken"].startswith("w_")


@pytest.mark.asyncio
async def test_create_session_accepts_configured_frontend_payload() -> None:
    async with asgi_http_client() as client:
        response = await client.post(
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


@pytest.mark.asyncio
async def test_create_session_preserves_auto_source_language() -> None:
    async with asgi_http_client() as client:
        response = await client.post(
            "/api/sessions",
            json={"inputMode": "browser_audio", "sourceLanguage": "auto", "targetLanguage": "zh"},
        )

    assert response.status_code == 200
    record = session_store.get(response.json()["sessionId"])
    assert record is not None
    assert record.source_language == "auto"
    assert record.target_language == "zh"


@pytest.mark.asyncio
async def test_mock_websocket_stream() -> None:
    async with asgi_http_client() as client:
        created = (await client.post("/api/sessions", json={"inputMode": "demo"})).json()
    session_id = created["sessionId"]

    async with ASGIWebSocketSession(
        f"/api/ws/sessions/{session_id}?token={created['wsToken']}"
    ) as websocket:
        assert await websocket.receive_json() == {
            "type": "session_started",
            "sessionId": session_id,
        }

        await websocket.send_json({"type": "start_session"})
        event_types = [(await websocket.receive_json())["type"] for _ in range(4)]

    assert event_types == [
        "source_sync_state",
        "transcript_segment",
        "translation_segment",
        "revision_event",
    ]


@pytest.mark.asyncio
async def test_mock_websocket_report_includes_emitted_segments() -> None:
    async with asgi_http_client() as client:
        created = (await client.post("/api/sessions", json={"inputMode": "demo"})).json()
    session_id = created["sessionId"]

    async with ASGIWebSocketSession(
        f"/api/ws/sessions/{session_id}?token={created['wsToken']}"
    ) as websocket:
        await websocket.receive_json()
        await websocket.send_json({"type": "start_session"})
        while True:
            event = await websocket.receive_json()
            if event["type"] == "session_report":
                report_id = event["reportId"]
                break

    async with asgi_http_client() as client:
        response = await client.get(f"/api/sessions/{session_id}/report")
    assert response.status_code == 200
    report = response.json()
    assert report["reportId"] == report_id
    assert report["metrics"]["segments"] == 1
    assert report["metrics"]["realtimeRevisions"] == 1
    assert report["durationText"] == "00:04"
    segment = report["segments"][0]
    assert segment["sourceText"].startswith("Today we are going to talk")
    assert segment["finalTranslation"]


@pytest.mark.asyncio
async def test_session_history_tracks_created_and_report_ready_sessions() -> None:
    async with asgi_http_client() as client:
        created = (
            await client.post(
                "/api/sessions",
                json={
                    "inputMode": "demo",
                    "sessionName": "History Demo",
                    "domain": "技术",
                    "productMode": "quick",
                },
            )
        ).json()
        initial = await client.get("/api/sessions/history")

    assert initial.status_code == 200
    first_entry = initial.json()["items"][0]
    assert first_entry["sessionId"] == created["sessionId"]
    assert first_entry["sessionName"] == "History Demo"
    assert first_entry["domain"] == "技术"
    assert first_entry["status"] == "created"
    assert first_entry["availableFormats"] == []

    async with ASGIWebSocketSession(
        f"/api/ws/sessions/{created['sessionId']}?token={created['wsToken']}"
    ) as websocket:
        await websocket.receive_json()
        await websocket.send_json({"type": "start_session"})
        while True:
            event = await websocket.receive_json()
            if event["type"] == "session_report":
                report_id = event["reportId"]
                break

    async with asgi_http_client() as client:
        history = await client.get(f"/api/sessions/history/{created['sessionId']}")

    assert history.status_code == 200
    entry = history.json()
    assert entry["reportId"] == report_id
    assert entry["status"] in {"fallback", "completed"}
    assert entry["segmentCount"] == 1
    assert entry["availableFormats"] == ["txt", "srt", "md", "json"]


@pytest.mark.asyncio
async def test_floating_history_replaces_generic_session_name() -> None:
    async with asgi_http_client() as client:
        created = (
            await client.post(
                "/api/sessions",
                json={
                    "inputMode": "system_audio",
                    "sourceKey": "system_audio",
                    "sessionName": "悬浮自采集",
                    "productMode": "floating",
                },
            )
        ).json()
        initial = await client.get(f"/api/sessions/history/{created['sessionId']}")

    assert initial.status_code == 200
    entry = initial.json()
    assert entry["sessionName"].startswith("悬浮同传_系统音频_")
    assert entry["sessionName"] != "悬浮自采集"

    async with ASGIWebSocketSession(
        f"/api/ws/sessions/{created['sessionId']}?token={created['wsToken']}"
    ) as websocket:
        await websocket.receive_json()
        await websocket.send_json({"type": "stop_session"})
        while True:
            event = await websocket.receive_json()
            if event["type"] == "session_report":
                break

    async with asgi_http_client() as client:
        report_response = await client.get(f"/api/sessions/{created['sessionId']}/report")
        history_response = await client.get(f"/api/sessions/history/{created['sessionId']}")

    assert report_response.status_code == 200
    report = report_response.json()
    assert report["sessionName"].startswith("悬浮同传_系统音频_")
    assert history_response.json()["sessionName"].startswith("悬浮同传_系统音频_")


@pytest.mark.asyncio
async def test_session_history_refreshes_pending_status_from_persisted_report() -> None:
    async with asgi_http_client() as client:
        created = (
            await client.post(
                "/api/sessions",
                json={
                    "inputMode": "demo",
                    "sessionName": "Pending Refresh",
                    "productMode": "quick",
                },
            )
        ).json()

    record = session_store.get(created["sessionId"])
    assert record is not None
    pending_report = {
        "reportId": f"{created['sessionId']}-report-test",
        "sessionId": created["sessionId"],
        "sessionName": "Pending Refresh",
        "domain": "通用",
        "sourceLanguage": "en",
        "targetLanguage": "zh",
        "durationMs": 1000,
        "durationText": "00:01",
        "generatedAt": "2026-06-17 10:00:00",
        "summary": "基础报告",
        "qualityNotes": "纠偏中",
        "glossaryHits": [],
        "metrics": {"segments": 1, "realtimeRevisions": 0, "finalRevisions": 0, "durationText": "00:01"},
        "segments": [],
        "finalRevisions": [],
        "realtimeRevisions": [],
        "correctionModel": None,
        "correctionStatus": "pending",
        "correctionError": "",
        "correctionElapsedMs": 0,
    }
    session_history_store.upsert_from_record(record, report=pending_report)

    completed_report = {
        **pending_report,
        "summary": "完整总结",
        "qualityNotes": "已完成",
        "metrics": {"segments": 1, "realtimeRevisions": 0, "finalRevisions": 1, "durationText": "00:01"},
        "finalRevisions": [{"segmentId": "s1", "beforeText": "a", "afterText": "b", "reason": "会后纠偏"}],
        "correctionModel": "qwen-plus",
        "correctionStatus": "completed",
        "correctionElapsedMs": 1200,
    }
    report_path = settings.report_dir / f"{pending_report['reportId']}.json"
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(completed_report, ensure_ascii=False), encoding="utf-8")

    async with asgi_http_client() as client:
        history = await client.get("/api/sessions/history")

    entry = next(item for item in history.json()["items"] if item["sessionId"] == created["sessionId"])
    assert entry["status"] == "completed"
    assert entry["correctionStatus"] == "completed"
    assert entry["finalRevisionCount"] == 1


@pytest.mark.asyncio
async def test_mock_websocket_pause_and_resume() -> None:
    async with asgi_http_client() as client:
        created = (await client.post("/api/sessions", json={"inputMode": "demo"})).json()

    async with ASGIWebSocketSession(
        f"/api/ws/sessions/{created['sessionId']}?token={created['wsToken']}"
    ) as websocket:
        await websocket.receive_json()

        await websocket.send_json({"type": "pause_session"})
        pause_event = await websocket.receive_json()
        assert pause_event["type"] == "source_sync_state"
        assert pause_event["state"]["status"] == "missing"

        await websocket.send_json({"type": "resume_session"})
        resume_event = await websocket.receive_json()
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


@pytest.mark.asyncio
async def test_issue_and_claim_session_handoff_token_once() -> None:
    async with asgi_http_client() as client:
        response = await client.post(
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

        claim_response = await client.post(
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

        reused = await client.post(
            "/api/sessions/handoff/claim", json={"token": issued["handoffToken"]}
        )
        assert reused.status_code == 409


@pytest.mark.asyncio
async def test_primary_websocket_requires_session_token() -> None:
    async with asgi_http_client() as client:
        created = (await client.post("/api/sessions", json={"inputMode": "demo"})).json()

    async with ASGIWebSocketSession(f"/api/ws/sessions/{created['sessionId']}") as websocket:
        assert await websocket.receive_json() == {
            "type": "error",
            "message": "Missing WebSocket token",
        }

    async with ASGIWebSocketSession(
        f"/api/ws/sessions/{created['sessionId']}?token=bad-token"
    ) as websocket:
        assert await websocket.receive_json() == {
            "type": "error",
            "message": "Invalid WebSocket token",
        }


@pytest.mark.asyncio
async def test_handoff_websocket_token_is_validated_for_handoff_replay() -> None:
    async with asgi_http_client() as client:
        issued = (await client.post("/api/sessions/ws-session/handoff", json={})).json()
        claim = (
            await client.post(
                "/api/sessions/handoff/claim", json={"token": issued["handoffToken"]}
            )
        ).json()

    async with ASGIWebSocketSession(claim["wsUrl"]) as websocket:
        assert await websocket.receive_json() == {
            "type": "session_started",
            "sessionId": "ws-session",
        }

    async with ASGIWebSocketSession("/api/ws/sessions/ws-session?token=bad-token") as websocket:
        assert await websocket.receive_json() == {
            "type": "error",
            "message": "Invalid WebSocket token",
        }


@pytest.mark.asyncio
async def test_handoff_websocket_receives_primary_session_events() -> None:
    async with asgi_http_client() as client:
        issued = (await client.post("/api/sessions/mirror-session/handoff", json={})).json()
        claim = (
            await client.post(
                "/api/sessions/handoff/claim", json={"token": issued["handoffToken"]}
            )
        ).json()
    primary_token = handoff_tokens.issue_ws_token("mirror-session", purpose="session")

    async with ASGIWebSocketSession(claim["wsUrl"]) as handoff:
        assert await handoff.receive_json() == {
            "type": "session_started",
            "sessionId": "mirror-session",
        }

        async with ASGIWebSocketSession(
            f"/api/ws/sessions/mirror-session?token={primary_token}"
        ) as primary:
            await primary.receive_json()
            await primary.send_json({"type": "start_session"})

            primary_event = await primary.receive_json()
            handoff_event = await handoff.receive_json()

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
