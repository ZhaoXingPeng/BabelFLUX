from app.services.mock_session import record_mock_event
from app.services.session_store import SessionRecord


def test_record_mock_event_merges_translation_and_updates_duration() -> None:
    record = SessionRecord(session_id="mock-session")

    record_mock_event(
        record,
        {
            "type": "transcript_segment",
            "segment": {"startMs": 100, "endMs": 1200, "text": "source", "status": "final"},
        },
    )
    record_mock_event(
        record,
        {
            "type": "translation_segment",
            "segment": {"startMs": 100, "endMs": 1200, "text": "译文", "status": "final"},
        },
    )

    assert len(record.segments) == 1
    assert record.segments[0].source_text == "source"
    assert record.segments[0].translation_text == "译文"
    assert record.segments[0].original_translation == "译文"
    assert record.duration_ms == 1200


def test_record_mock_event_persists_revision_against_latest_translation() -> None:
    record = SessionRecord(session_id="mock-session")
    record_mock_event(
        record,
        {
            "type": "translation_segment",
            "segment": {"startMs": 0, "endMs": 500, "text": "初译", "status": "final"},
        },
    )

    record_mock_event(
        record,
        {
            "type": "revision_event",
            "revision": {
                "revisionId": "rev-1",
                "beforeText": "初译",
                "afterText": "终译",
                "reason": "术语统一",
                "confidence": 0.95,
            },
        },
    )

    assert record.segments[0].translation_text == "终译"
    assert record.segments[0].status == "revised"
    assert record.revisions[0].revision_id == "rev-1"
    assert record.revisions[0].target_segment_ids == [record.segments[0].segment_id]
    assert record.revisions[0].source == "mock"
