import sourceSubtitleText from "./source.en.txt?raw";
import targetSubtitleText from "./target.zh.txt?raw";
import { buildBilingualTimeline } from "../testVideo/subtitleTimeline";

const durationMs = 176_123;
const segments = buildBilingualTimeline(sourceSubtitleText, targetSubtitleText, durationMs, "en", "zh");

export const englishTestVideoFixture = {
  key: "fixture-video-en",
  label: "TED 英文测试视频",
  videoUrl: "/fixtures/english-test-video/video.mp4",
  audioUrl: "/fixtures/english-test-video/voice.mp3",
  sourceSubtitleUrl: "/fixtures/english-test-video/source.en.txt",
  targetSubtitleUrl: "/fixtures/english-test-video/target.zh.txt",
  sourceLanguage: "en",
  targetLanguage: "zh",
  durationMs,
  segments,
  revisions: []
} as const;
