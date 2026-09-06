import { describe, expect, it } from "vitest";
import { englishTestVideoFixture } from "../fixtures/englishTestVideo";
import { testVideoFixture } from "../fixtures/testVideo";
import {
  createFixtureSourceSegments,
  currentFixture,
  defaultFixture,
  fixturePlaybackState,
  fixtureSessionId,
  isFixtureSession,
  isFixtureSource
} from "./sessionFixture";

describe("session fixture state", () => {
  it("selects known fixtures and keeps an unknown source on the default fixture", () => {
    expect(isFixtureSource(englishTestVideoFixture.key)).toBe(true);
    expect(isFixtureSource("url")).toBe(false);
    expect(currentFixture("unknown")).toBe(defaultFixture);
    expect(isFixtureSession(fixtureSessionId(englishTestVideoFixture))).toBe(true);
    expect(isFixtureSession("local-test-video-fixture")).toBe(true);
  });

  it("derives a partial first subtitle after the output latency", () => {
    const state = fixturePlaybackState(testVideoFixture, 1000);
    const first = testVideoFixture.segments[0];

    expect(state.activeSegmentId).toBe(first.segmentId);
    expect(state.sourceSegments).toHaveLength(1);
    expect(state.sourceSegments[0]).toMatchObject({ segmentId: first.segmentId, status: "partial" });
    expect(state.sourceSegments[0].text.length).toBeLessThanOrEqual(first.source.length);
    expect(state.speech).toMatchObject({ segmentId: first.segmentId, text: first.target });
  });

  it("applies due fixture revisions to subtitle output and speech", () => {
    const revision = testVideoFixture.revisions[0];
    expect(revision).toBeDefined();
    if (!revision) return;

    const state = fixturePlaybackState(testVideoFixture, revision.atMs);
    const translation = state.translationSegments.find((segment) => segment.segmentId === revision.segmentId);

    expect(translation).toMatchObject({
      text: revision.afterText,
      status: "revised",
      originalText: revision.beforeText,
      revisionReason: revision.reason
    });
    expect(state.fixtureAppliedRevisionIds).toContain(revision.revisionId);
    expect(state.revisions[0]?.revisionId).toBe(revision.revisionId);
  });

  it("creates complete segments for an initial fixture preview", () => {
    const source = createFixtureSourceSegments(testVideoFixture);

    expect(source).toHaveLength(testVideoFixture.segments.length);
    expect(source[0]).toMatchObject({
      segmentId: testVideoFixture.segments[0]?.segmentId,
      status: "final",
      language: testVideoFixture.sourceLanguage
    });
  });
});
