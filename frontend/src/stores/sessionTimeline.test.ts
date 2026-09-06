import { describe, expect, it } from "vitest";
import type { SubtitleSegment } from "../types/events";
import {
  activeSegmentForPlayback,
  applyRevisionToSegments,
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

  it("applies a revision to every target while preserving unrelated segments", () => {
    const source = [segment("a", 0, 1000), segment("b", 1000, 2000)];
    const translation = [segment("a", 0, 1000, "old a"), segment("b", 1000, 2000, "old b")];
    const revision = {
      revisionId: "r1",
      targetSegmentIds: ["a", "b"],
      beforeText: "old",
      afterText: "new",
      reason: "术语统一",
      confidence: 0.9
    };

    const updated = applyRevisionToSegments(source, translation, revision);

    expect(updated.sourceSegments.map((item) => item.status)).toEqual(["revised", "revised"]);
    expect(updated.translationSegments[0]).toMatchObject({
      text: "new",
      status: "revised",
      originalText: "old",
      revisionReason: "术语统一"
    });
    expect(updated.sourceSegments).not.toBe(source);
    expect(updated.translationSegments).not.toBe(translation);
  });

  it("leaves all segments untouched when the revision has no matching target", () => {
    const source = [segment("a", 0, 1000)];
    const translation = [segment("a", 0, 1000, "stable")];
    const revision = {
      revisionId: "r2",
      targetSegmentIds: ["missing"],
      beforeText: "old",
      afterText: "new",
      reason: "不适用",
      confidence: 0.1
    };

    expect(applyRevisionToSegments(source, translation, revision)).toEqual({
      sourceSegments: source,
      translationSegments: translation
    });
  });

  it("keeps a pending current segment during output latency hold", () => {
    const source = [segment("a", 0, 1000, "current"), segment("b", 1200, 1800, "next")];
    const translation = [segment("b", 1200, 1800, "next translation")];
    expect(activeSegmentForPlayback(source, translation, 2300, 0)).toBe("b");
    expect(shouldKeepCurrentActiveSegment(source, translation, "a", "b", 1300, false, 0)).toBe(true);
  });
});
