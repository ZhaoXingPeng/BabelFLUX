import { englishTestVideoFixture } from "../fixtures/englishTestVideo";
import {
  findActiveSegment,
  testVideoFixture,
  type TestVideoRevision
} from "../fixtures/testVideo";
import type { RevisionEvent, SegmentStatus, SubtitleSegment } from "../types/events";

export const FIXTURE_SUBTITLE_LATENCY_MS = 1000;

type VideoFixture = typeof testVideoFixture | typeof englishTestVideoFixture;

export interface FixturePlaybackState {
  activeSegmentId: string | null;
  fixtureAppliedRevisionIds: string[];
  revisions: RevisionEvent[];
  sourceSegments: SubtitleSegment[];
  translationSegments: SubtitleSegment[];
  speech: {
    segmentId: string;
    text: string;
    targetLanguage: string;
  } | null;
}

export const videoFixtures: VideoFixture[] = [testVideoFixture, englishTestVideoFixture];
const fixtureByKey = new Map<string, VideoFixture>(videoFixtures.map((fixture) => [fixture.key, fixture]));

export const defaultFixture = testVideoFixture;

export function isFixtureSource(sourceKey: string): boolean {
  return fixtureByKey.has(sourceKey);
}

export function currentFixture(sourceKey: string): VideoFixture {
  return fixtureByKey.get(sourceKey) ?? defaultFixture;
}

export function createFixtureSourceSegments(
  fixture: VideoFixture = defaultFixture
): SubtitleSegment[] {
  return fixture.segments.map((segment) => ({
    segmentId: segment.segmentId,
    text: segment.source,
    language: fixture.sourceLanguage,
    startMs: segment.startMs,
    endMs: segment.endMs,
    status: "final"
  }));
}

export function createFixtureTranslationSegments(
  fixture: VideoFixture = defaultFixture
): SubtitleSegment[] {
  return fixture.segments.map((segment) => ({
    segmentId: segment.segmentId,
    text: segment.target,
    language: fixture.targetLanguage,
    startMs: segment.startMs,
    endMs: segment.endMs,
    status: "final"
  }));
}

function createFixtureRevisionEvent(revision: TestVideoRevision): RevisionEvent {
  return {
    revisionId: revision.revisionId,
    targetSegmentIds: [revision.segmentId],
    beforeText: revision.beforeText,
    afterText: revision.afterText,
    reason: revision.reason,
    confidence: revision.confidence
  };
}

export function fixtureSessionId(fixture: VideoFixture): string {
  return `local-${fixture.key}`;
}

export function isFixtureSession(sessionId: string | null): boolean {
  return (
    sessionId === "local-test-video-fixture" ||
    videoFixtures.some((fixture) => sessionId === fixtureSessionId(fixture))
  );
}

function streamText(text: string, progress: number): string {
  const value = text.trim();
  if (!value || progress >= 0.98) return value;
  const units = /\s/.test(value) ? value.split(/(\s+)/).filter(Boolean) : Array.from(value);
  const visible = Math.max(1, Math.ceil(units.length * (0.18 + clamp01(progress) * 0.82)));
  return units.slice(0, visible).join("");
}

function clamp01(value: number): number {
  return Math.min(1, Math.max(0, value));
}

/** Derives the local demonstration state from one playback position without mutating the store. */
export function fixturePlaybackState(
  fixture: VideoFixture,
  playbackMs: number,
  subtitleLatencyMs = FIXTURE_SUBTITLE_LATENCY_MS,
  partialWindowMs = 900
): FixturePlaybackState {
  const effectiveMs = playbackMs - subtitleLatencyMs;
  const revealed = fixture.segments.filter((segment) => effectiveMs >= segment.startMs);
  const activeSegment = findActiveSegment(fixture.segments, effectiveMs);
  const activeSegmentId = activeSegment?.segmentId ?? revealed[revealed.length - 1]?.segmentId ?? null;
  const revealedIds = new Set(revealed.map((segment) => segment.segmentId));
  const dueRevisions = fixture.revisions.filter(
    (revision) => playbackMs >= revision.atMs && revealedIds.has(revision.segmentId)
  );
  const revisionBySegment = new Map(dueRevisions.map((revision) => [revision.segmentId, revision] as const));
  const isFreshActive = (segmentId: string, startMs: number) =>
    segmentId === activeSegmentId && effectiveMs - startMs < partialWindowMs;

  const sourceSegments = revealed.map((segment) => ({
    segmentId: segment.segmentId,
    text: isFreshActive(segment.segmentId, segment.startMs)
      ? streamText(segment.source, (effectiveMs - segment.startMs) / partialWindowMs)
      : segment.source,
    language: fixture.sourceLanguage,
    startMs: segment.startMs,
    endMs: segment.endMs,
    status: (isFreshActive(segment.segmentId, segment.startMs) ? "partial" : "final") as SegmentStatus
  }));

  const translationSegments = revealed.map((segment) => {
    const revision = revisionBySegment.get(segment.segmentId);
    if (revision) {
      return {
        segmentId: segment.segmentId,
        text: revision.afterText,
        language: fixture.targetLanguage,
        startMs: segment.startMs,
        endMs: segment.endMs,
        status: "revised" as const,
        originalText: revision.beforeText,
        revisionReason: revision.reason
      };
    }
    return {
      segmentId: segment.segmentId,
      text: isFreshActive(segment.segmentId, segment.startMs)
        ? streamText(segment.target, (effectiveMs - segment.startMs) / partialWindowMs)
        : segment.target,
      language: fixture.targetLanguage,
      startMs: segment.startMs,
      endMs: segment.endMs,
      status: (isFreshActive(segment.segmentId, segment.startMs) ? "partial" : "final") as SegmentStatus
    };
  });

  const activeRevision = activeSegment ? revisionBySegment.get(activeSegment.segmentId) : undefined;
  return {
    activeSegmentId,
    fixtureAppliedRevisionIds: dueRevisions.map((revision) => revision.revisionId),
    revisions: dueRevisions.map(createFixtureRevisionEvent).reverse(),
    sourceSegments,
    translationSegments,
    speech: activeSegment
      ? {
          segmentId: activeRevision?.revisionId ?? activeSegment.segmentId,
          text: activeRevision?.afterText ?? activeSegment.target,
          targetLanguage: fixture.targetLanguage
        }
      : null
  };
}
