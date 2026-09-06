import { bench, describe } from "vitest";
import type { SubtitleSegment } from "../types/events";
import { buildTranscriptPairs } from "./transcriptPairs";

function segment(segmentId: string, startMs: number): SubtitleSegment {
  return {
    segmentId,
    text: segmentId,
    language: "en",
    startMs,
    endMs: startMs + 1000,
    status: "final"
  };
}

const sourceSegments = Array.from({ length: 2000 }, (_, index) => segment(`segment-${index}`, index * 1000));
const translationSegments = sourceSegments.map((item) => ({
  ...item,
  language: "zh",
  text: `译文-${item.segmentId}`
}));

function naiveTranscriptPairs(source: SubtitleSegment[], translation: SubtitleSegment[]) {
  const ids: string[] = [];
  [...source, ...translation].forEach((item) => {
    if (!ids.includes(item.segmentId)) ids.push(item.segmentId);
  });
  return ids.map((segmentId) => {
    const sourceSegment = source.find((item) => item.segmentId === segmentId);
    const translationSegment = translation.find((item) => item.segmentId === segmentId);
    return {
      segmentId,
      time: `${sourceSegment?.startMs ?? translationSegment?.startMs ?? 0}ms`,
      source: sourceSegment?.text ?? "",
      translation: translationSegment?.text ?? "",
      state: translationSegment?.status ?? sourceSegment?.status ?? "partial",
      isActive: false
    };
  });
}

describe("transcript pair aggregation", () => {
  bench("baseline: includes + find", () => {
    naiveTranscriptPairs(sourceSegments, translationSegments);
  });

  bench("optimized: map aggregation", () => {
    buildTranscriptPairs(sourceSegments, translationSegments, {
      activeSegmentId: null,
      hasSession: true,
      formatTime: (milliseconds) => `${milliseconds}ms`,
      samplePairs: []
    });
  });
});
