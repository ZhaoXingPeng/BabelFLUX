import chineseSubtitleText from "./ch.txt?raw";
import englishSubtitleText from "./en.txt?raw";
import { buildBilingualTimeline } from "./subtitleTimeline";

export interface TestVideoRevision {
  revisionId: string;
  segmentId: string;
  atMs: number;
  beforeText: string;
  afterText: string;
  reason: string;
  confidence: number;
}

const durationMs = 136_301;
const segments = buildBilingualTimeline(englishSubtitleText, chineseSubtitleText, durationMs);
// 纠偏演示段：约 10 秒处的「a few ... her own mark」。译文先按字面出，
// 待上下文（博物馆 / 画家回顾展）到位后于约 13 秒自动校正，贴近真实的实时纠偏节奏。
const revisionSegment = segments.find((segment) => segment.startMs === 10_000);

export const testVideoRevisions: TestVideoRevision[] = revisionSegment
  ? [
      {
        revisionId: "fixture-rev-context",
        segmentId: revisionSegment.segmentId,
        atMs: 13_000,
        beforeText: revisionSegment.zh,
        afterText: "她告诉我，有几幅作品没能完全达到她自己的标准，",
        reason: "结合上下文：a few 指几幅画作，own mark 应译作「自己的标准」",
        confidence: 0.95
      }
    ]
  : [];

export const testVideoFixture = {
  key: "fixture-video",
  label: "默认测试视频",
  videoUrl: "/fixtures/test-video/video.mp4",
  audioUrl: "/fixtures/test-video/voice.m4a",
  englishSubtitleUrl: "/fixtures/test-video/en.txt",
  chineseSubtitleUrl: "/fixtures/test-video/ch.txt",
  durationMs,
  segments,
  revisions: testVideoRevisions
} as const;

export { buildBilingualTimeline, findActiveSegment, parseTimedSubtitleText, parseTimestamp } from "./subtitleTimeline";
