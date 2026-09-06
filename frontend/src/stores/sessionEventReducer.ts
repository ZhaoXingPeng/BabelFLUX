import type {
  RevisionEvent,
  ServerEvent,
  SourceSyncState,
  SubtitleSegment
} from "../types/events";
import {
  activeSegmentForPlayback,
  applyRevisionToSegments,
  shouldKeepCurrentActiveSegment,
  upsertSegment
} from "./sessionTimeline";

export interface LiveSubtitleState {
  sourceSyncState: SourceSyncState;
  playbackMs: number;
  activeSegmentId: string | null;
  sourceSegments: SubtitleSegment[];
  translationSegments: SubtitleSegment[];
  revisions: RevisionEvent[];
}

export interface LiveSubtitleReducerOptions {
  outputLatencyMs: number;
  pendingTranslationHoldMs?: number;
  updateActiveSegment?: boolean;
}

function nextActiveSegmentId(
  state: LiveSubtitleState,
  playbackMs: number,
  outputLatencyMs: number,
  pendingTranslationHoldMs: number
): string | null {
  const candidateId = activeSegmentForPlayback(
    state.sourceSegments,
    state.translationSegments,
    playbackMs,
    outputLatencyMs
  );
  return shouldKeepCurrentActiveSegment(
    state.sourceSegments,
    state.translationSegments,
    state.activeSegmentId,
    candidateId,
    playbackMs,
    false,
    outputLatencyMs,
    pendingTranslationHoldMs
  )
    ? state.activeSegmentId
    : candidateId;
}

/** Applies server subtitle events without mutating state or performing I/O. */
export function reduceLiveSubtitleEvent(
  state: LiveSubtitleState,
  event: ServerEvent,
  options: LiveSubtitleReducerOptions
): LiveSubtitleState {
  const updateActiveSegment = options.updateActiveSegment ?? true;
  const pendingTranslationHoldMs = options.pendingTranslationHoldMs ?? 2600;

  if (event.type === "source_sync_state") {
    return {
      ...state,
      sourceSyncState: event.state,
      playbackMs:
        typeof event.state.sourceMs === "number" ? event.state.sourceMs : state.playbackMs
    };
  }

  if (event.type === "transcript_segment") {
    const nextState = {
      ...state,
      sourceSegments: upsertSegment(state.sourceSegments, event.segment)
    };
    return updateActiveSegment
      ? {
          ...nextState,
          activeSegmentId: nextActiveSegmentId(
            nextState,
            state.playbackMs,
            options.outputLatencyMs,
            pendingTranslationHoldMs
          )
        }
      : nextState;
  }

  if (event.type === "translation_segment") {
    const nextState = {
      ...state,
      translationSegments: upsertSegment(state.translationSegments, event.segment)
    };
    return updateActiveSegment
      ? {
          ...nextState,
          activeSegmentId: nextActiveSegmentId(
            nextState,
            state.playbackMs,
            options.outputLatencyMs,
            pendingTranslationHoldMs
          )
        }
      : nextState;
  }

  if (event.type === "revision_event") {
    const updated = applyRevisionToSegments(
      state.sourceSegments,
      state.translationSegments,
      event.revision
    );
    return {
      ...state,
      ...updated,
      revisions: [event.revision, ...state.revisions].slice(0, 20)
    };
  }

  return state;
}
