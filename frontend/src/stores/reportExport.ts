import type { ReportFormat, SessionReport } from "../api/client";

function srtTimestamp(ms: number): string {
  const clamped = Math.max(0, ms);
  const h = Math.floor(clamped / 3_600_000);
  const m = Math.floor((clamped % 3_600_000) / 60_000);
  const s = Math.floor((clamped % 60_000) / 1000);
  const millis = clamped % 1000;
  const pad = (value: number, len = 2) => String(value).padStart(len, "0");
  return `${pad(h)}:${pad(m)}:${pad(s)},${pad(millis, 3)}`;
}

/** 客户端报告渲染（本地演示下载用，与后端 report.py 的 txt/srt/md/json 对齐）。 */
export function renderReportClient(
  report: SessionReport,
  format: ReportFormat
): { body: string; mime: string; ext: string } {
  if (format === "json") {
    return { body: JSON.stringify(report, null, 2), mime: "application/json", ext: "json" };
  }
  if (format === "srt") {
    const body = report.segments
      .map((seg, index) => {
        const end = seg.endMs > seg.startMs ? seg.endMs : seg.startMs + 2000;
        return `${index + 1}\n${srtTimestamp(seg.startMs)} --> ${srtTimestamp(end)}\n${seg.sourceText}\n${seg.finalTranslation}\n`;
      })
      .join("\n");
    return { body, mime: "application/x-subrip", ext: "srt" };
  }
  if (format === "md") {
    const lines = [
      `# ${report.sessionName}`,
      "",
      `- **领域**：${report.domain}`,
      `- **语言**：${report.sourceLanguage} → ${report.targetLanguage}`,
      `- **时长**：${report.durationText}`,
      `- **句数**：${report.metrics.segments}　实时修正：${report.metrics.realtimeRevisions}　会后修正：${report.metrics.finalRevisions}`,
      `- **全文纠偏**：${correctionStatusText(report)}`,
      "",
      "## 摘要",
      report.summary,
      "",
      "## 双语终稿",
      "",
      "| 时间 | 原文 | 终稿译文 |",
      "| --- | --- | --- |",
      ...report.segments.map(
        (seg) =>
          `| ${seg.timecode} | ${seg.sourceText.replace(/\|/g, "\\|")} | ${seg.finalTranslation.replace(/\|/g, "\\|")} |`
      )
    ];
    if (report.finalRevisions.length) {
      lines.push("", "## 会后校正记录", "", "| 原译文 | 校正后 | 原因 |", "| --- | --- | --- |");
      report.finalRevisions.forEach((rev) => {
        lines.push(
          `| ${rev.beforeText.replace(/\|/g, "\\|")} | ${rev.afterText.replace(/\|/g, "\\|")} | ${rev.reason} |`
        );
      });
    } else if (report.correctionStatus === "completed") {
      lines.push("", "## 会后校正记录", "", "全文纠偏已完成，本场未发现需要改写的译文。");
    }
    if (report.qualityNotes) {
      lines.push("", "## 质量说明", report.qualityNotes);
    }
    return { body: lines.join("\n"), mime: "text/markdown", ext: "md" };
  }
  const lines = [
    `# ${report.sessionName}`,
    `领域：${report.domain}  |  语言：${report.sourceLanguage} -> ${report.targetLanguage}  |  时长：${report.durationText}`,
    `生成时间：${report.generatedAt}`,
    `全文纠偏：${correctionStatusText(report)}`,
    "",
    "【摘要】",
    report.summary,
    "",
    "【双语终稿】",
    ...report.segments.flatMap((seg) => [`[${seg.timecode}] ${seg.sourceText}`, `          ${seg.finalTranslation}`])
  ];
  if (report.finalRevisions.length) {
    lines.push("", "【会后校正记录】");
    report.finalRevisions.forEach((rev) => lines.push(`- ${rev.beforeText}  =>  ${rev.afterText}  （${rev.reason}）`));
  } else if (report.correctionStatus === "completed") {
    lines.push("", "【会后校正记录】", "全文纠偏已完成，本场未发现需要改写的译文。");
  }
  if (report.qualityNotes) {
    lines.push("", "【质量说明】", report.qualityNotes);
  }
  return { body: lines.join("\n"), mime: "text/plain", ext: "txt" };
}

function correctionStatusText(report: SessionReport): string {
  if (report.correctionStatus === "pending") return "基础报告已可下载，全文纠偏生成中";
  const elapsedMs = report.correctionElapsedMs ?? 0;
  const elapsed = elapsedMs > 0 ? `，耗时 ${(elapsedMs / 1000).toFixed(1)} 秒` : "";
  const model = report.correctionModel ? `，模型 ${report.correctionModel}` : "";
  if (report.correctionStatus === "completed") return `已完成${model}${elapsed}`;
  if (report.correctionStatus === "partial") return `部分完成${model}${elapsed}`;
  if (report.correctionStatus === "timeout") return `超时降级${elapsed}`;
  if (report.correctionStatus === "skipped") return "未执行";
  return report.correctionModel ? `已完成${model}${elapsed}` : `降级为实时译文${elapsed}`;
}
