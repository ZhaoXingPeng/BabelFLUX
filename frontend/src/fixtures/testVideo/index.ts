import sourceSubtitleText from "./source.zh.txt?raw";
import targetSubtitleText from "./target.en.txt?raw";
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

const durationMs = 176_610;
const segments = buildBilingualTimeline(sourceSubtitleText, targetSubtitleText, durationMs, "zh", "en");
// 纠偏演示段：约 17 秒处的“长期睡眠不足”先按直译输出，
// 待上下文（学生作业负担）到位后于约 23 秒自动校正，贴近真实的实时纠偏节奏。
const revisionSegment = segments.find((segment) => segment.startMs === 17_000);

export const testVideoRevisions: TestVideoRevision[] = revisionSegment
  ? [
      {
        revisionId: "fixture-rev-context",
        segmentId: revisionSegment.segmentId,
        atMs: 23_000,
        beforeText: revisionSegment.target,
        afterText: "A while ago, during a class, a student told me that one of their grade-mates had long been sleep-deprived.",
        reason: "结合上下文：长期睡眠不足指学生长期缺觉，而不是普通的 short on sleep",
        confidence: 0.95
      }
    ]
  : [];

export const testVideoFixture = {
  key: "fixture-video",
  label: "中文测试视频",
  videoUrl: "/fixtures/test-video/video.mp4",
  audioUrl: "/fixtures/test-video/voice.mp3",
  sourceSubtitleUrl: "/fixtures/test-video/source.zh.txt",
  targetSubtitleUrl: "/fixtures/test-video/target.en.txt",
  sourceLanguage: "zh",
  targetLanguage: "en",
  durationMs,
  segments,
  revisions: testVideoRevisions
} as const;

export { buildBilingualTimeline, findActiveSegment, parseTimedSubtitleText, parseTimestamp } from "./subtitleTimeline";
