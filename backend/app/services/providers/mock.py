from typing import Any


def build_mock_events(session_id: str) -> list[dict[str, Any]]:
    return [
        {
            "type": "source_sync_state",
            "state": {"status": "synced", "lagMs": 180, "message": "源语言字幕同步正常"},
        },
        {
            "type": "transcript_segment",
            "segment": {
                "segmentId": f"{session_id}-src-1",
                "text": "Today we are going to talk about real-time AI translation.",
                "language": "en",
                "startMs": 0,
                "endMs": 4200,
                "status": "final",
            },
        },
        {
            "type": "translation_segment",
            "segment": {
                "segmentId": f"{session_id}-zh-1",
                "text": "今天我们要讨论实时 AI 翻译。",
                "language": "zh",
                "startMs": 0,
                "endMs": 4200,
                "status": "final",
            },
        },
        {
            "type": "revision_event",
            "revision": {
                "revisionId": f"{session_id}-rev-1",
                "targetSegmentIds": [f"{session_id}-zh-1"],
                "beforeText": "实时人工智能翻译",
                "afterText": "实时 AI 翻译",
                "reason": "术语表命中",
                "confidence": 0.92,
            },
        },
    ]
