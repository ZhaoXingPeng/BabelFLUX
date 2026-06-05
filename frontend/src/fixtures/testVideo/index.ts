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
const nearWinSegment = segments.find((segment) => segment.startMs === 46_000);

export const testVideoRevisions: TestVideoRevision[] = nearWinSegment
  ? [
      {
        revisionId: "fixture-rev-near-win",
        segmentId: nearWinSegment.segmentId,
        atMs: 52_000,
        beforeText: nearWinSegment.zh,
        afterText: "我想，当我们开始珍视一次差一点成功的馈赠时，转变就发生了，",
        reason: "语义纠偏：near win 不是“险胜”",
        confidence: 0.94
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
