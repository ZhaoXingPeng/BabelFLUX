"""演示会话事件播放与记录适配。"""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from typing import Any

from app.services.providers.mock import build_mock_events
from app.services.session_store import RevisionRecord, SegmentRecord, SessionRecord

EventEmitter = Callable[[dict[str, Any]], Awaitable[None]]


async def run_mock_session(record: SessionRecord, emit: EventEmitter) -> None:
    for event in build_mock_events(record.session_id):
        record_mock_event(record, event)
        await emit(event)
        await asyncio.sleep(0.25)


def record_mock_event(record: SessionRecord, event: dict[str, Any]) -> None:
    event_type = event.get("type")
    if event_type in {"transcript_segment", "translation_segment"}:
        payload = event.get("segment") or {}
        seg = _mock_record_segment(record, payload)
        text = str(payload.get("text") or "")
        status = str(payload.get("status") or "partial")
        if event_type == "transcript_segment":
            seg.source_text = text
            if not seg.translation_text:
                seg.status = status
        else:
            seg.translation_text = text
            if not seg.original_translation:
                seg.original_translation = text
            seg.status = status
        record.duration_ms = max(record.duration_ms, seg.end_ms)
        return

    if event_type == "revision_event":
        payload = event.get("revision") or {}
        target = next((seg for seg in reversed(record.segments) if seg.translation_text), None)
        if target is None:
            return
        before_text = str(payload.get("beforeText") or target.translation_text)
        after_text = str(payload.get("afterText") or target.translation_text)
        target.original_translation = target.original_translation or before_text
        target.translation_text = after_text
        target.status = "revised"
        target.revised = True
        target.revision_reason = str(payload.get("reason") or "")
        record.revisions.append(
            RevisionRecord(
                revision_id=str(payload.get("revisionId") or f"{record.session_id}-mock-rev"),
                target_segment_ids=[target.segment_id],
                before_text=before_text,
                after_text=after_text,
                reason=target.revision_reason,
                confidence=float(payload.get("confidence") or 0),
                source="mock",
                created_ms=target.end_ms,
            )
        )


def _mock_record_segment(record: SessionRecord, payload: dict[str, Any]) -> SegmentRecord:
    start_ms = int(payload.get("startMs") or 0)
    end_ms = int(payload.get("endMs") or start_ms)
    for seg in record.segments:
        if seg.start_ms == start_ms and seg.end_ms == end_ms:
            return seg

    index = len(record.segments) + 1
    seg = record.get_or_create_segment(f"{record.session_id}-mock-{index}", index)
    seg.start_ms = start_ms
    seg.end_ms = end_ms
    return seg
