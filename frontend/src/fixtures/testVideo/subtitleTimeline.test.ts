import { describe, expect, it } from "vitest";
import { findActiveSegment, testVideoFixture } from ".";
import sourceSubtitleText from "./source.zh.txt?raw";
import targetSubtitleText from "./target.en.txt?raw";
import { buildBilingualTimeline, parseTimedSubtitleText, parseTimestamp } from "./subtitleTimeline";

describe("test video subtitle timeline", () => {
  it("解析 mm:ss 时间戳", () => {
    expect(parseTimestamp("00:46")).toBe(46_000);
    expect(parseTimestamp("01:14")).toBe(74_000);
    expect(parseTimestamp("00:02:10")).toBe(130_000);
  });

  it("把源文和译文字幕按行对齐并补齐结束时间", () => {
    const sourceLines = parseTimedSubtitleText(sourceSubtitleText);
    const targetLines = parseTimedSubtitleText(targetSubtitleText);
    const segments = buildBilingualTimeline(sourceSubtitleText, targetSubtitleText, testVideoFixture.durationMs);

    expect(segments).toHaveLength(Math.min(sourceLines.length, targetLines.length));
    expect(segments[0]).toMatchObject({
      segmentId: "fixture-seg-001",
      startMs: 0,
      endMs: 2_000,
      source: "我今天就是要站出来，"
    });
    expect(segments[0].target).toContain("standing up");
    expect(segments[segments.length - 1].endMs).toBe(testVideoFixture.durationMs);
  });

  it("按播放时间查找当前字幕段", () => {
    const active = findActiveSegment(testVideoFixture.segments, 52_000);

    expect(active?.startMs).toBe(52_000);
    expect(active?.source).toContain("为什么会做这么久");
  });
});
