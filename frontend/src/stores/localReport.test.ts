import { describe, expect, it } from "vitest";
import { buildLocalReport } from "./localReport";

describe("buildLocalReport", () => {
  it("builds deterministic metrics and preserves realtime corrections", () => {
    const report = buildLocalReport({
      sessionId: "fixture-session",
      sessionName: "演示报告",
      domain: "技术",
      sourceLanguage: "英语",
      targetLanguage: "中文",
      durationMs: 65_000,
      generatedAt: "2026-09-07 10:00:00",
      pairs: [
        {
          segmentId: "s1",
          time: "00:01",
          source: "The token is invalid.",
          translation: "令牌无效。",
          originalTranslation: "令牌不正确。",
          state: "revised"
        },
        {
          time: "00:02",
          source: "temporary",
          translation: "临时",
          state: "partial"
        }
      ],
      revisions: [
        {
          revisionId: "r1",
          targetSegmentIds: ["s1"],
          beforeText: "令牌不正确。",
          afterText: "令牌无效。",
          reason: "术语统一",
          confidence: 0.95
        }
      ]
    });

    expect(report.sessionId).toBe("fixture-session");
    expect(report.durationText).toBe("01:05");
    expect(report.generatedAt).toBe("2026-09-07 10:00:00");
    expect(report.metrics).toEqual({
      segments: 1,
      realtimeRevisions: 1,
      finalRevisions: 0,
      durationText: "01:05"
    });
    expect(report.segments[0]).toMatchObject({
      segmentId: "s1",
      liveTranslation: "令牌不正确。",
      finalTranslation: "令牌无效。",
      revisedRealtime: true
    });
    expect(report.finalRevisions).toHaveLength(1);
    expect(report.realtimeRevisions[0].stage).toBe("实时");
    expect(report.correctionStatus).toBe("skipped");
  });

  it("uses a local fallback name and handles an empty transcript", () => {
    const report = buildLocalReport({
      sessionId: null,
      sessionName: "",
      domain: "通用",
      sourceLanguage: "自动检测",
      targetLanguage: "中文",
      durationMs: 0,
      generatedAt: "固定时间",
      pairs: [],
      revisions: []
    });

    expect(report.sessionName).toBe("本地演示报告");
    expect(report.segments).toEqual([]);
    expect(report.summary).toContain("共 0 句");
    expect(report.finalRevisions).toEqual([]);
  });
});
