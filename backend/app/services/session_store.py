"""会话运行期状态存储（进程内）。

记录每个同传会话的配置、累计的源/译文段落与修正事件，以及会后生成的报告。
管线运行时写入；REST 报告接口与会后完整纠偏从这里读取。

单机部署、演示场景下用进程内字典即可；如需多进程/持久化可换 Redis/SQLite。
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from threading import Lock
from typing import Any


@dataclass
class SegmentRecord:
    segment_id: str
    index: int
    start_ms: int = 0
    end_ms: int = 0
    source_text: str = ""
    translation_text: str = ""
    # 译文最初产出值（用于会后对照「实时 vs 校正」）
    original_translation: str = ""
    status: str = "partial"  # partial | final | revised
    revised: bool = False
    revision_reason: str = ""
    # LiveTranslate 关联：源用输入 item_id，译文用 response_id（输出 item 与源 item 不同）
    item_id: str | None = None
    response_id: str | None = None


@dataclass
class RevisionRecord:
    revision_id: str
    target_segment_ids: list[str]
    before_text: str
    after_text: str
    reason: str
    confidence: float
    source: str = "llm"  # llm | glossary | refine
    created_ms: int = 0


@dataclass
class SessionRecord:
    session_id: str
    source_language: str = "en"
    target_language: str = "zh"
    domain: str = "通用"
    session_name: str = "未命名同传"
    glossary: list[dict[str, Any]] = field(default_factory=list)
    tts_enabled: bool = False
    input_mode: str = "demo"
    source_label: str = ""
    source_url: str | None = None
    media_path: str | None = None
    created_at: float = field(default_factory=time.time)
    ended_at: float | None = None
    duration_ms: int = 0
    segments: list[SegmentRecord] = field(default_factory=list)
    revisions: list[RevisionRecord] = field(default_factory=list)
    report: dict[str, Any] | None = None
    status: str = "created"  # created | running | ended | error
    _by_id: dict[str, SegmentRecord] = field(default_factory=dict)

    def get_or_create_segment(self, segment_id: str, index: int) -> SegmentRecord:
        record = self._by_id.get(segment_id)
        if record is None:
            record = SegmentRecord(segment_id=segment_id, index=index)
            self._by_id[segment_id] = record
            self.segments.append(record)
        return record

    def finalized_segments(self) -> list[SegmentRecord]:
        return [s for s in self.segments if s.status in ("final", "revised") and s.source_text]

    def reportable_segments(self) -> list[SegmentRecord]:
        return [s for s in self.segments if s.source_text and s.translation_text]


class SessionStore:
    def __init__(self) -> None:
        self._sessions: dict[str, SessionRecord] = {}
        self._lock = Lock()

    def create(self, session_id: str, **kwargs: Any) -> SessionRecord:
        with self._lock:
            record = SessionRecord(session_id=session_id, **kwargs)
            self._sessions[session_id] = record
            return record

    def get(self, session_id: str) -> SessionRecord | None:
        return self._sessions.get(session_id)

    def get_or_create(self, session_id: str, **kwargs: Any) -> SessionRecord:
        existing = self._sessions.get(session_id)
        if existing is not None:
            return existing
        return self.create(session_id, **kwargs)

    def remove(self, session_id: str) -> None:
        with self._lock:
            self._sessions.pop(session_id, None)


# 进程内单例
session_store = SessionStore()
