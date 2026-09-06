import { describe, expect, it } from "vitest";
import type { SubtitleSegment } from "../types/events";
import { reduceDesktopCaptionEvent, type DesktopCaptionState } from "./desktopCaptionTimeline";

const segment = (
  segmentId: string,
  startMs: number,
  text: string,
  status: SubtitleSegment["status"] = "partial"
): SubtitleSegment => ({
  segmentId,
  startMs,
  endMs: startMs + 1000,
  text,
  language: "en",
  status
});

const initialState = (): DesktopCaptionState => ({
  pair: { time: "00:00", source: "", translation: "", state: "partial", isActive: true },
  lastStartMs: -1
});

describe("desktop caption timeline", () => {
  it("merges source and translation events for the same segment", () => {
    const source = reduceDesktopCaptionEvent(
      initialState(),
      { type: "transcript_segment", segment: segment("a", 1000, "hello") }
    );
    const next = reduceDesktopCaptionEvent(
      source,
      { type: "translation_segment", segment: segment("a", 1000, "你好", "final") }
    );

    expect(next.pair).toMatchObject({ segmentId: "a", source: "hello", translation: "你好", state: "final" });
  });

  it("ignores an older segment arriving after the current segment", () => {
    const current = reduceDesktopCaptionEvent(
      initialState(),
      { type: "translation_segment", segment: segment("new", 2000, "new") }
    );

    const next = reduceDesktopCaptionEvent(
      current,
      { type: "transcript_segment", segment: segment("old", 1000, "old") }
    );

    expect(next).toBe(current);
  });

  it("applies revisions only to the current segment", () => {
    const current = reduceDesktopCaptionEvent(
      initialState(),
      { type: "translation_segment", segment: segment("a", 1000, "old", "final") }
    );
    const unrelated = reduceDesktopCaptionEvent(current, {
      type: "revision_event",
      revision: {
        revisionId: "r-old",
        targetSegmentIds: ["old"],
        beforeText: "old",
        afterText: "wrong",
        reason: "不相关",
        confidence: 0.8
      }
    });
    const revised = reduceDesktopCaptionEvent(current, {
      type: "revision_event",
      revision: {
        revisionId: "r-a",
        targetSegmentIds: ["a"],
        beforeText: "old",
        afterText: "new",
        reason: "术语统一",
        confidence: 0.9
      }
    });

    expect(unrelated).toBe(current);
    expect(revised.pair).toMatchObject({ translation: "new", state: "revised" });
    expect(current.pair.translation).toBe("old");
  });
});
