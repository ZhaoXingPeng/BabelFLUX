import asyncio

from app.services.session_events import SessionEventHub


def _drain(queue: asyncio.Queue[dict[str, object]]) -> list[dict[str, object]]:
    events: list[dict[str, object]] = []
    while not queue.empty():
        events.append(queue.get_nowait())
    return events


def test_subscriber_overflow_drops_oldest_audio_before_control_events() -> None:
    hub = SessionEventHub(history_limit=10, queue_size=3)
    subscription = hub.subscribe("session")

    hub.publish("session", {"type": "audio_segment", "segmentId": "a1"})
    hub.publish("session", {"type": "translation_segment", "segmentId": "s1"})
    hub.publish("session", {"type": "audio_segment", "segmentId": "a2"})
    hub.publish("session", {"type": "session_report", "reportId": "r1"})

    assert [event["type"] for event in _drain(subscription.queue)] == [
        "translation_segment",
        "audio_segment",
        "session_report",
    ]


def test_subscriber_overflow_without_audio_keeps_bounded_fifo_fallback() -> None:
    hub = SessionEventHub(history_limit=10, queue_size=2)
    subscription = hub.subscribe("session")

    hub.publish("session", {"type": "translation_segment", "segmentId": "s1"})
    hub.publish("session", {"type": "revision_event", "revisionId": "v1"})
    hub.publish("session", {"type": "session_report", "reportId": "r1"})

    assert [event["type"] for event in _drain(subscription.queue)] == [
        "revision_event",
        "session_report",
    ]


def test_history_replay_prioritizes_control_events_and_deep_copies_payloads() -> None:
    hub = SessionEventHub(history_limit=2, queue_size=2)
    payload = {"type": "audio_segment", "segmentId": "a1", "meta": {"value": 1}}
    hub.publish("session", payload)
    payload["meta"]["value"] = 99
    hub.publish("session", {"type": "translation_segment", "segmentId": "s1"})
    hub.publish("session", {"type": "session_report", "reportId": "r1"})

    replay = hub.subscribe("session").replay
    assert [event["type"] for event in replay] == ["translation_segment", "session_report"]
