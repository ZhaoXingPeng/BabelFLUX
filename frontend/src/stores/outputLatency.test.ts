import { describe, expect, it } from "vitest";
import { createOutputLatencyTracker } from "./outputLatency";

const createTracker = () =>
  createOutputLatencyTracker({
    fallbackMs: 1000,
    minMs: 250,
    maxMs: 6000,
    sampleSize: 3
  });

describe("output latency tracker", () => {
  it("starts at the fallback and records valid samples", () => {
    const tracker = createTracker();

    expect(tracker.estimateMs).toBe(1000);
    tracker.record("a", 1000, 1400);
    tracker.record("b", 2000, 2600);

    expect(tracker.estimateMs).toBe(600);
  });

  it("ignores duplicate, invalid, and out-of-range samples", () => {
    const tracker = createTracker();

    tracker.record("duplicate", 1000, 1500);
    tracker.record("duplicate", 1000, 2500);
    tracker.record("negative", -1, 500);
    tracker.record("too-small", 1000, 1100);
    tracker.record("too-large", 1000, 8000);

    expect(tracker.estimateMs).toBe(500);
  });

  it("keeps a bounded sample window and resets all state", () => {
    const tracker = createTracker();

    tracker.record("a", 0, 400);
    tracker.record("b", 0, 600);
    tracker.record("c", 0, 800);
    tracker.record("d", 0, 1200);
    expect(tracker.estimateMs).toBe(800);

    tracker.reset();
    expect(tracker.estimateMs).toBe(1000);
    tracker.record("a", 0, 500);
    expect(tracker.estimateMs).toBe(500);
  });
});
