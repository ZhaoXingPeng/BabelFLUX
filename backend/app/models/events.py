from typing import Literal

from pydantic import BaseModel, Field


class SourceSyncState(BaseModel):
    status: Literal["synced", "lagging", "missing", "idle"]
    lag_ms: int = Field(alias="lagMs")
    message: str


class SubtitleSegment(BaseModel):
    segment_id: str = Field(alias="segmentId")
    text: str
    language: str
    start_ms: int = Field(alias="startMs")
    end_ms: int = Field(alias="endMs")
    status: Literal["partial", "final", "revised"]


class RevisionEvent(BaseModel):
    revision_id: str = Field(alias="revisionId")
    target_segment_ids: list[str] = Field(alias="targetSegmentIds")
    before_text: str = Field(alias="beforeText")
    after_text: str = Field(alias="afterText")
    reason: str
    confidence: float
