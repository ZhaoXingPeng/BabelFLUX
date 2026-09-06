import type { RevisionEvent } from "../types/events";
import type { TranscriptPair } from "../types/workflow";
import type { SessionReport } from "../api/client";

export interface BuildLocalReportInput {
  sessionId: string | null;
  sessionName: string;
  domain: string;
  sourceLanguage: string;
  targetLanguage: string;
  durationMs: number;
  generatedAt: string;
  pairs: TranscriptPair[];
  revisions: RevisionEvent[];
}

function formatPlaybackTime(ms: number): string {
  const totalSeconds = Math.floor(ms / 1000);
  const minutes = Math.floor(totalSeconds / 60);
  const seconds = totalSeconds % 60;
  return `${String(minutes).padStart(2, "0")}:${String(seconds).padStart(2, "0")}`;
}

export function buildLocalReport(input: BuildLocalReportInput): SessionReport {
  const durationText = formatPlaybackTime(input.durationMs);
  const segments = input.pairs
    .filter((pair) => pair.segmentId)
    .map((pair, index) => ({
      segmentId: pair.segmentId ?? `local-${index}`,
      startMs: 0,
      endMs: 0,
      timecode: pair.time,
      sourceText: pair.source,
      liveTranslation: pair.originalTranslation ?? pair.translation,
      finalTranslation: pair.translation,
      revisedRealtime: pair.state === "revised"
    }));
  const realtimeRevisions = input.revisions.map((revision) => ({
    segmentId: revision.targetSegmentIds[0] ?? "",
    beforeText: revision.beforeText,
    afterText: revision.afterText,
    reason: revision.reason,
    stage: "实时"
  }));

  return {
    reportId: "",
    sessionId: input.sessionId ?? "",
    sessionName: input.sessionName || "本地演示报告",
    domain: input.domain,
    sourceLanguage: input.sourceLanguage,
    targetLanguage: input.targetLanguage,
    durationMs: input.durationMs,
    durationText,
    generatedAt: input.generatedAt,
    summary: `本地测试素材演示：共 ${segments.length} 句，含 ${realtimeRevisions.length} 处自动纠偏。`,
    qualityNotes: "本地演示报告由前端依据测试素材合成，未经后端大模型完整纠偏。",
    glossaryHits: [],
    metrics: {
      segments: segments.length,
      realtimeRevisions: realtimeRevisions.length,
      finalRevisions: 0,
      durationText
    },
    segments,
    finalRevisions: realtimeRevisions,
    realtimeRevisions,
    correctionModel: null,
    correctionStatus: "skipped",
    correctionError: "本地演示报告未调用后端会后完整纠偏。",
    correctionElapsedMs: 0
  };
}
