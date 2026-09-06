import type { ServerEvent, SubtitleSegment } from "../types/events";
import type { TranscriptPair } from "../types/workflow";

export interface DesktopCaptionState {
  pair: TranscriptPair;
  lastStartMs: number;
}

function formatTime(ms: number): string {
  const totalSeconds = Math.floor(Math.max(0, ms) / 1000);
  return `${String(Math.floor(totalSeconds / 60)).padStart(2, "0")}:${String(totalSeconds % 60).padStart(2, "0")}`;
}

function isOlderSegment(state: DesktopCaptionState, segment: SubtitleSegment): boolean {
  return Boolean(
    state.pair.segmentId &&
      state.pair.segmentId !== segment.segmentId &&
      segment.startMs < state.lastStartMs
  );
}

function mergeSegment(
  state: DesktopCaptionState,
  segment: SubtitleSegment,
  field: "source" | "translation"
): DesktopCaptionState {
  if (isOlderSegment(state, segment)) return state;

  const sameSegment = state.pair.segmentId === segment.segmentId;
  const startMs = sameSegment ? Math.max(state.lastStartMs, segment.startMs) : segment.startMs;
  const pair: TranscriptPair = sameSegment
    ? { ...state.pair }
    : {
        segmentId: segment.segmentId,
        time: formatTime(startMs),
        source: "",
        translation: "",
        state: segment.status,
        isActive: true
      };
  pair.segmentId = segment.segmentId;
  pair[field] = segment.text;
  pair.time = formatTime(startMs);
  pair.state = segment.status;
  pair.isActive = true;
  return { pair, lastStartMs: startMs };
}

/** Applies desktop caption events without mutating the previous state or doing I/O. */
export function reduceDesktopCaptionEvent(
  state: DesktopCaptionState,
  event: ServerEvent
): DesktopCaptionState {
  if (event.type === "transcript_segment") return mergeSegment(state, event.segment, "source");
  if (event.type === "translation_segment") {
    return mergeSegment(state, event.segment, "translation");
  }
  if (event.type !== "revision_event") return state;

  const currentId = state.pair.segmentId;
  if (currentId && !event.revision.targetSegmentIds.includes(currentId)) return state;
  return {
    pair: {
      ...state.pair,
      translation: event.revision.afterText,
      state: "revised",
      originalTranslation: event.revision.beforeText,
      revisionReason: event.revision.reason,
      isActive: true
    },
    lastStartMs: state.lastStartMs
  };
}
