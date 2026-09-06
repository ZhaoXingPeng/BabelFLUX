import { describe, expect, it } from "vitest";
import type { SessionReport } from "../api/client";
import { renderReportClient } from "./reportExport";

const report: SessionReport = {
  reportId: "report-1",
  sessionId: "session-1",
  sessionName: "技术分享",
  domain: "技术",
  sourceLanguage: "en",
  targetLanguage: "zh",
  modelProfile: "高准确",
  durationMs: 2500,
  durationText: "00:02",
  generatedAt: "2026-09-07 03:00:00",
  summary: "介绍流式架构",
  qualityNotes: "术语已统一",
  glossaryHits: [],
  metrics: { segments: 1, realtimeRevisions: 1, finalRevisions: 1, durationText: "00:02" },
  segments: [
    {
      segmentId: "seg-1",
      startMs: 0,
      endMs: 0,
      timecode: "00:00:00,000",
      sourceText: "A | B",
      liveTranslation: "甲",
      finalTranslation: "甲和乙",
      revisedRealtime: false
    }
  ],
  finalRevisions: [
    { segmentId: "seg-1", beforeText: "甲", afterText: "甲和乙", reason: "补全术语" }
  ],
  realtimeRevisions: [],
  correctionModel: "qwen-plus",
  correctionStatus: "completed",
  correctionElapsedMs: 1200
};

describe("renderReportClient", () => {
  it("renders JSON without changing the report payload", () => {
    const rendered = renderReportClient(report, "json");

    expect(rendered).toMatchObject({ mime: "application/json", ext: "json" });
    expect(JSON.parse(rendered.body)).toEqual(report);
  });

  it("renders SRT with a two-second fallback for zero-length segments", () => {
    const rendered = renderReportClient(report, "srt");

    expect(rendered).toMatchObject({ mime: "application/x-subrip", ext: "srt" });
    expect(rendered.body).toContain("00:00:00,000 --> 00:00:02,000");
    expect(rendered.body).toContain("A | B\n甲和乙");
  });

  it("renders Markdown tables with escaped separators and revision details", () => {
    const rendered = renderReportClient(report, "md");

    expect(rendered).toMatchObject({ mime: "text/markdown", ext: "md" });
    expect(rendered.body).toContain("| A \\| B | 甲和乙 |");
    expect(rendered.body).toContain("| 甲 | 甲和乙 | 补全术语 |");
    expect(rendered.body).toContain("已完成");
  });

  it("renders TXT with summary, revisions, and quality notes", () => {
    const rendered = renderReportClient(report, "txt");

    expect(rendered).toMatchObject({ mime: "text/plain", ext: "txt" });
    expect(rendered.body).toContain("【摘要】\n介绍流式架构");
    expect(rendered.body).toContain("- 甲  =>  甲和乙  （补全术语）");
    expect(rendered.body).toContain("【质量说明】\n术语已统一");
  });
});
