import { describe, expect, it } from "vitest";
import type { SubtitleSegment } from "../types/events";
import {
  activeSegmentForPlayback,
  mergeSegmentUpdate,
  shouldKeepCurrentActiveSegment,
  upsertSegment
} from "./sessionTimeline";

const segment = (segmentId: string, startMs: number, endMs: number, text = "text"): SubtitleSegment => ({
  segmentId,
  text,
  language: "en",
  startMs,
  endMs,
  status: "final"
});

describe("session timeline", () => {
  it("preserves stable timing when a partial update regresses", () => {
    const previous = segment("a", 1000, 2000);
    const next = { ...segment("a", 0, 0), status: "partial" as const };
    expect(mergeSegmentUpdate(previous, next)).toMatchObject({ startMs: 1000, endMs: 2000 });
  });

  it("upserts by id without changing unrelated segments", () => {
    const first = segment("a", 0, 1000);
    const second = segment("b", 1000, 2000);
    expect(upsertSegment([first, second], { ...first, text: "updated" })).toEqual([
      { ...first, text: "updated" },
      second
    ]);
  });

  it("keeps a pending current segment during output latency hold", () => {
    const source = [segment("a", 0, 1000, "current"), segment("b", 1200, 1800, "next")];
    const translation = [segment("b", 1200, 1800, "next translation")];
    expect(activeSegmentForPlayback(source, translation, 2300, 0)).toBe("b");
    expect(shouldKeepCurrentActiveSegment(source, translation, "a", "b", 1300, false, 0)).toBe(true);
  });
});
