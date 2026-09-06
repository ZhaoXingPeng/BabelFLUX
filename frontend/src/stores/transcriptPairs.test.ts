import { describe, expect, it } from "vitest";
import type { SubtitleSegment } from "../types/events";
import { buildTranscriptPairs } from "./transcriptPairs";

function segment(
  segmentId: string,
  text: string,
  startMs: number,
  status: SubtitleSegment["status"] = "final"
): SubtitleSegment {
  return {
    segmentId,
    text,
    language: "en",
    startMs,
    endMs: startMs + 1000,
    status
  };
}

const options = (activeSegmentId: string | null, hasSession = true) => ({
  activeSegmentId,
  hasSession,
  formatTime: (milliseconds: number) => `${milliseconds}ms`,
  samplePairs: [
    {
      segmentId: "sample",
      time: "0ms",
      source: "sample",
      translation: "示例",
      state: "final"
    }
  ]
});

describe("buildTranscriptPairs", () => {
  it("merges source and translation by id while preserving source-first order", () => {
    const pairs = buildTranscriptPairs(
      [segment("a", "hello", 100), segment("b", "world", 200)],
      [segment("a", "你好", 100), segment("c", "extra", 300)],
      options("b")
    );

    expect(pairs.map((pair) => pair.segmentId)).toEqual(["a", "b", "c"]);
    expect(pairs.find((pair) => pair.segmentId === "a")).toMatchObject({
      source: "hello",
      translation: "你好",
      time: "100ms"
    });
  });

  it("keeps only the active source-only partial pair", () => {
    const pairs = buildTranscriptPairs(
      [segment("active", "pending", 100, "partial"), segment("old", "old pending", 200, "partial")],
      [],
      options("active")
    );

    expect(pairs.map((pair) => pair.segmentId)).toEqual(["active"]);
    expect(pairs[0].state).toBe("partial");
  });

  it("preserves revision metadata and revised state", () => {
    const translation = {
      ...segment("a", "修正后", 100, "revised"),
      originalText: "原译文",
      revisionReason: "术语"
    };
    const [pair] = buildTranscriptPairs([segment("a", "source", 100)], [translation], options("a"));

    expect(pair).toMatchObject({
      state: "revised",
      originalTranslation: "原译文",
      revisionReason: "术语"
    });
  });

  it("returns session-empty or preview fallback states unchanged", () => {
    const previewOptions = options(null, false);
    expect(buildTranscriptPairs([], [], previewOptions)).toBe(previewOptions.samplePairs);
    expect(buildTranscriptPairs([], [], options(null, true))).toEqual([]);
  });
});
