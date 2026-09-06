import { describe, expect, it } from "vitest";
import type { SubtitleSegment } from "../types/events";
import { reduceLiveSubtitleEvent, type LiveSubtitleState } from "./sessionEventReducer";

const segment = (
  segmentId: string,
  startMs: number,
  endMs: number,
  text: string,
  status: SubtitleSegment["status"] = "final"
): SubtitleSegment => ({
  segmentId,
  startMs,
  endMs,
  text,
  language: "en",
  status
});

const state = (): LiveSubtitleState => ({
  sourceSyncState: { status: "listening", lagMs: 0, message: "等待" },
  playbackMs: 1200,
  activeSegmentId: null,
  sourceSegments: [],
  translationSegments: [],
  revisions: []
});

const options = { outputLatencyMs: 0 };

describe("session event reducer", () => {
  it("updates source clock without mutating the previous state", () => {
    const previous = state();
    const next = reduceLiveSubtitleEvent(
      previous,
      { type: "source_sync_state", state: { status: "syncing", lagMs: 20, message: "同步", sourceMs: 2400 } },
      options
    );

    expect(next.playbackMs).toBe(2400);
    expect(next.sourceSyncState.status).toBe("syncing");
    expect(previous.playbackMs).toBe(1200);
  });

  it("upserts segments, computes the active segment, and preserves input arrays", () => {
    const previous = state();
    const next = reduceLiveSubtitleEvent(
      previous,
      { type: "transcript_segment", segment: segment("a", 1000, 2000, "hello") },
      options
    );

    expect(next.sourceSegments).toHaveLength(1);
    expect(next.activeSegmentId).toBe("a");
    expect(previous.sourceSegments).toEqual([]);
  });

  it("applies revisions and keeps only the newest twenty records", () => {
    const previous = state();
    previous.translationSegments = [segment("a", 1000, 2000, "old")];
    const revision = {
      revisionId: "r1",
      targetSegmentIds: ["a"],
      beforeText: "old",
      afterText: "new",
      reason: "术语统一",
      confidence: 0.9
    };

    const next = reduceLiveSubtitleEvent(
      previous,
      { type: "revision_event", revision },
      options
    );

    expect(next.translationSegments[0]).toMatchObject({ text: "new", status: "revised" });
    expect(next.revisions).toEqual([revision]);
    expect(previous.translationSegments[0]?.text).toBe("old");
  });

  it("ignores side-effect events and unknown state changes", () => {
    const previous = state();
    const next = reduceLiveSubtitleEvent(
      previous,
      { type: "audio_segment", segmentId: "a", audioBase64: "AA==", sampleRate: 24000 },
      options
    );

    expect(next).toBe(previous);
  });
});
