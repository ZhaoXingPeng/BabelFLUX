import { describe, expect, it } from "vitest";
import { findActiveSegment, testVideoFixture } from ".";
import chineseSubtitleText from "./ch.txt?raw";
import englishSubtitleText from "./en.txt?raw";
import { buildBilingualTimeline, parseTimedSubtitleText, parseTimestamp } from "./subtitleTimeline";

describe("test video subtitle timeline", () => {
  it("解析 mm:ss 时间戳", () => {
    expect(parseTimestamp("00:46")).toBe(46_000);
    expect(parseTimestamp("01:14")).toBe(74_000);
    expect(parseTimestamp("00:02:10")).toBe(130_000);
  });

  it("把中英字幕按行对齐并补齐结束时间", () => {
    const englishLines = parseTimedSubtitleText(englishSubtitleText);
    const chineseLines = parseTimedSubtitleText(chineseSubtitleText);
    const segments = buildBilingualTimeline(englishSubtitleText, chineseSubtitleText, testVideoFixture.durationMs);

    expect(segments).toHaveLength(Math.min(englishLines.length, chineseLines.length));
    expect(segments[0]).toMatchObject({
      segmentId: "fixture-seg-001",
      startMs: 0,
      endMs: 4_000,
      en: "I feel so fortunate that my first job was working at the museum of modern art,"
    });
    expect(segments[0].zh).toContain("我感到很幸运");
    expect(segments[segments.length - 1].endMs).toBe(testVideoFixture.durationMs);
  });

  it("按播放时间查找当前字幕段", () => {
    const active = findActiveSegment(testVideoFixture.segments, 52_000);

    expect(active?.startMs).toBe(52_000);
    expect(active?.en).toContain("How many times");
  });
});
