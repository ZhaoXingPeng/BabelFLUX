import type { SubtitleSegment } from "../types/events";

export interface TimelineSegment {
  segmentId: string;
  startMs: number;
  endMs: number;
}

function hasStableTiming(segment: SubtitleSegment): boolean {
  return Number.isFinite(segment.startMs) && Number.isFinite(segment.endMs) && segment.endMs > segment.startMs;
}

export function mergeSegmentUpdate(previous: SubtitleSegment, next: SubtitleSegment): SubtitleSegment {
  let startMs = next.startMs;
  let endMs = next.endMs;

  if (hasStableTiming(previous)) {
    const incomingStable = hasStableTiming(next);
    if (!incomingStable || (previous.startMs > 0 && next.startMs <= 0)) {
      startMs = previous.startMs;
      endMs = previous.endMs;
    } else if (next.status === "partial" && next.startMs + 500 < previous.startMs) {
      startMs = previous.startMs;
      endMs = Math.max(previous.endMs, next.endMs);
    }
  }

  if (!Number.isFinite(endMs) || endMs <= startMs) {
    endMs = hasStableTiming(previous) ? previous.endMs : startMs;
  }

  return { ...previous, ...next, startMs, endMs };
}

export function upsertSegment(items: SubtitleSegment[], segment: SubtitleSegment): SubtitleSegment[] {
  const index = items.findIndex((item) => item.segmentId === segment.segmentId);
  if (index === -1) return [...items, segment];
  return items.map((item, itemIndex) => (itemIndex === index ? mergeSegmentUpdate(item, segment) : item));
}

export function combinedTimeline(
  sourceSegments: SubtitleSegment[],
  translationSegments: SubtitleSegment[]
): TimelineSegment[] {
  const byId = new Map<string, { source?: SubtitleSegment; translation?: SubtitleSegment }>();
  for (const source of sourceSegments) {
    const entry = byId.get(source.segmentId) ?? {};
    if (!entry.source) entry.source = source;
    byId.set(source.segmentId, entry);
  }
  for (const translation of translationSegments) {
    const entry = byId.get(translation.segmentId) ?? {};
    if (!entry.translation) entry.translation = translation;
    byId.set(translation.segmentId, entry);
  }

  return Array.from(byId, ([segmentId, { source, translation }]) => ({
    segmentId,
    startMs: source?.startMs ?? translation?.startMs ?? 0,
    endMs: Math.max(source?.endMs ?? 0, translation?.endMs ?? 0)
  }))
    .sort((a, b) => a.startMs - b.startMs);
}

export function activeSegmentForPlayback(
  sourceSegments: SubtitleSegment[],
  translationSegments: SubtitleSegment[],
  playbackMs: number,
  outputLatencyMs: number
): string | null {
  const timeline = combinedTimeline(sourceSegments, translationSegments);
  if (timeline.length === 0) return null;

  const displayClockMs = Math.max(0, playbackMs - outputLatencyMs);
  const enriched = timeline.map((segment, index) => {
    const next = timeline[index + 1];
    return {
      ...segment,
      endMs: Math.max(segment.endMs, next?.startMs ?? 0, segment.startMs + 2000)
    };
  });
  const exact = enriched.find(
    (segment) => displayClockMs >= segment.startMs && displayClockMs < segment.endMs
  );
  if (exact) return exact.segmentId;
  return [...enriched].reverse().find((segment) => segment.startMs <= displayClockMs)?.segmentId
    ?? enriched[enriched.length - 1]?.segmentId
    ?? null;
}

function hasTranslationText(translationSegments: SubtitleSegment[], segmentId: string | null): boolean {
  if (!segmentId) return false;
  return Boolean(translationSegments.find((segment) => segment.segmentId === segmentId)?.text.trim());
}

function hasPendingTranslation(
  sourceSegments: SubtitleSegment[],
  translationSegments: SubtitleSegment[],
  segmentId: string | null
): boolean {
  if (!segmentId) return false;
  const source = sourceSegments.find((segment) => segment.segmentId === segmentId);
  const translation = translationSegments.find((segment) => segment.segmentId === segmentId);
  return Boolean(source?.text.trim()) && !translation?.text.trim();
}

function timelineSegmentById(
  sourceSegments: SubtitleSegment[],
  translationSegments: SubtitleSegment[],
  segmentId: string | null
): TimelineSegment | undefined {
  if (!segmentId) return undefined;
  return combinedTimeline(sourceSegments, translationSegments).find((segment) => segment.segmentId === segmentId);
}

export function shouldKeepCurrentActiveSegment(
  sourceSegments: SubtitleSegment[],
  translationSegments: SubtitleSegment[],
  currentId: string | null,
  candidateId: string | null,
  playbackMs: number,
  allowBackward: boolean,
  outputLatencyMs: number,
  pendingTranslationHoldMs = 2600
): boolean {
  if (allowBackward || !currentId || !candidateId || currentId === candidateId) return false;
  const current = timelineSegmentById(sourceSegments, translationSegments, currentId);
  const candidate = timelineSegmentById(sourceSegments, translationSegments, candidateId);
  if (!current || !candidate) return false;
  if (hasPendingTranslation(sourceSegments, translationSegments, currentId)) {
    const holdUntil = Math.max(current.endMs, current.startMs + 1200)
      + outputLatencyMs
      + pendingTranslationHoldMs;
    if (playbackMs <= holdUntil && candidate.startMs > current.startMs) return true;
  }
  if (
    hasTranslationText(translationSegments, currentId) &&
    hasPendingTranslation(sourceSegments, translationSegments, candidateId)
  ) {
    const currentEnd = Math.max(current.endMs, current.startMs + 1200);
    const candidateSource = sourceSegments.find((segment) => segment.segmentId === candidateId);
    const candidateTextLength = candidateSource?.text.trim().length ?? 0;
    const candidateLooksFragment = candidateTextLength < 24 || candidate.endMs - candidate.startMs <= 1400;
    if (
      candidateLooksFragment &&
      candidate.startMs <= currentEnd + 400 &&
      playbackMs <= currentEnd + outputLatencyMs + 800
    ) {
      return true;
    }
  }
  return candidate.startMs + 500 < current.startMs && playbackMs >= current.startMs - 500;
}
