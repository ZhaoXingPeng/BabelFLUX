export type SessionStatus = "idle" | "connecting" | "running" | "stopped" | "error";

export type SegmentStatus = "partial" | "final" | "revised";

export interface SourceSyncState {
  status: "listening" | "syncing" | "lagging" | "missing" | "recovered";
  lagMs: number;
  message: string;
}

export interface SubtitleSegment {
  segmentId: string;
  text: string;
  language: string;
  startMs: number;
  endMs: number;
  status: SegmentStatus;
}

export interface RevisionEvent {
  revisionId: string;
  targetSegmentIds: string[];
  beforeText: string;
  afterText: string;
  reason: string;
  confidence: number;
}

export type ServerEvent =
  | { type: "session_started"; sessionId: string }
  | { type: "source_sync_state"; state: SourceSyncState }
  | { type: "transcript_segment"; segment: SubtitleSegment }
  | { type: "translation_segment"; segment: SubtitleSegment }
  | { type: "revision_event"; revision: RevisionEvent }
  | { type: "session_report"; reportId: string }
  | { type: "error"; message: string };
