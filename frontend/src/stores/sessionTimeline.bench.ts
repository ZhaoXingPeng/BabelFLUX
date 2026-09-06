import { bench, describe } from "vitest";
import type { SubtitleSegment } from "../types/events";
import { combinedTimeline } from "./sessionTimeline";

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
const translationSegments = sourceSegments.map((item) => ({ ...item, language: "zh", text: `译文-${item.segmentId}` }));

function naiveCombinedTimeline(
  source: SubtitleSegment[],
  translation: SubtitleSegment[]
) {
  const ids: string[] = [];
  [...source, ...translation].forEach((item) => {
    if (!ids.includes(item.segmentId)) ids.push(item.segmentId);
  });
  return ids
    .map((segmentId) => {
      const sourceSegment = source.find((item) => item.segmentId === segmentId);
      const translationSegment = translation.find((item) => item.segmentId === segmentId);
      return {
        segmentId,
        startMs: sourceSegment?.startMs ?? translationSegment?.startMs ?? 0,
        endMs: Math.max(sourceSegment?.endMs ?? 0, translationSegment?.endMs ?? 0)
      };
    })
    .sort((a, b) => a.startMs - b.startMs);
}

describe("session timeline aggregation", () => {
  bench("baseline: includes + find", () => {
    naiveCombinedTimeline(sourceSegments, translationSegments);
  });

  bench("optimized: map aggregation", () => {
    combinedTimeline(sourceSegments, translationSegments);
  });
});
