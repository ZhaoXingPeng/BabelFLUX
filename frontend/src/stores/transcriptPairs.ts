import type { SubtitleSegment } from "../types/events";
import type { TranscriptPair } from "../types/workflow";

interface TranscriptPairEntry {
  source?: SubtitleSegment;
  translation?: SubtitleSegment;
}

export interface BuildTranscriptPairsOptions {
  activeSegmentId: string | null;
  hasSession: boolean;
  formatTime: (milliseconds: number) => string;
  samplePairs: TranscriptPair[];
}

/**
 * Merge source and translation updates in insertion order without rescanning
 * either segment list for every ID.
 */
export function buildTranscriptPairs(
  sourceSegments: SubtitleSegment[],
  translationSegments: SubtitleSegment[],
  options: BuildTranscriptPairsOptions
): TranscriptPair[] {
  if (sourceSegments.length === 0 && translationSegments.length === 0) {
    return options.hasSession ? [] : options.samplePairs;
  }

  const byId = new Map<string, TranscriptPairEntry>();
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

  return Array.from(byId, ([segmentId, { source, translation }]) => {
    const sourceStatus = source?.status;
    const translationStatus = translation?.status;
    const state =
      translationStatus === "revised"
        ? "revised"
        : sourceStatus === "partial" || translationStatus === "partial"
          ? "partial"
          : (translationStatus ?? sourceStatus ?? "partial");
    const startMs = source?.startMs ?? translation?.startMs ?? 0;
    return {
      segmentId,
      time: options.formatTime(startMs),
      source: source?.text ?? "",
      translation: translation?.text ?? "",
      state,
      isActive: segmentId === options.activeSegmentId,
      originalTranslation: translation?.originalText,
      revisionReason: translation?.revisionReason
    };
  }).filter((pair) => {
    if (pair.translation.trim()) return true;
    if (!pair.source.trim()) return false;
    return pair.segmentId === options.activeSegmentId;
  });
}
