from typing import Any

from app.models.events import RevisionEvent, SourceSyncState, SubtitleSegment


def build_mock_events(session_id: str) -> list[dict[str, Any]]:
    """构造演示用事件流。

    所有 payload 都由 app.models.events 的 Pydantic 模型产出（model_dump(by_alias=True)），
    以保证 mock 发出的事件结构始终符合事件模型——事件模型是前后端事件契约的单一事实源。
    """
    sync_state = SourceSyncState(status="syncing", lagMs=180, message="源语言字幕同步正常")
    transcript = SubtitleSegment(
        segmentId=f"{session_id}-src-1",
        text="Today we are going to talk about real-time AI translation.",
        language="en",
        startMs=0,
        endMs=4200,
        status="final",
    )
    translation = SubtitleSegment(
        segmentId=f"{session_id}-zh-1",
        text="今天我们要讨论实时 AI 翻译。",
        language="zh",
        startMs=0,
        endMs=4200,
        status="final",
    )
    revision = RevisionEvent(
        revisionId=f"{session_id}-rev-1",
        targetSegmentIds=[f"{session_id}-zh-1"],
        beforeText="实时人工智能翻译",
        afterText="实时 AI 翻译",
        reason="术语表命中",
        confidence=0.92,
    )
    return [
        {"type": "source_sync_state", "state": sync_state.model_dump(by_alias=True)},
        {"type": "transcript_segment", "segment": transcript.model_dump(by_alias=True)},
        {"type": "translation_segment", "segment": translation.model_dump(by_alias=True)},
        {"type": "revision_event", "revision": revision.model_dump(by_alias=True)},
    ]
