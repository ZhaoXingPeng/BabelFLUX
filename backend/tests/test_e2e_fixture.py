from app.services.providers.mock import build_mock_events


def test_mock_pipeline_end_to_end() -> None:
    """验证 mock 模式完整链路：同步状态 -> 字幕 -> 译文 -> 纠偏。"""
    events = build_mock_events("test-session")
    event_types = [event["type"] for event in events]

    assert len(events) >= 4
    assert event_types == [
        "source_sync_state",
        "transcript_segment",
        "translation_segment",
        "revision_event",
    ]
    assert "audio_segment" not in event_types

    transcript = events[1]["segment"]
    translation = events[2]["segment"]
    assert transcript["language"] == "en"
    assert translation["language"] == "zh"
    assert transcript["startMs"] == translation["startMs"]
    assert transcript["endMs"] == translation["endMs"]


def test_tts_not_enabled_in_mock() -> None:
    """mock 模式默认不合成 TTS，因此不会产生 audio_segment。"""
    events = build_mock_events("mock-no-tts")

    assert all(event["type"] != "audio_segment" for event in events)
