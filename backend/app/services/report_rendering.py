"""Pure renderers for session reports.

Report generation owns model calls and report assembly; this module only turns
the resulting dictionary into user-downloadable text formats.
"""

from __future__ import annotations

from typing import Any


def format_timecode(ms: int) -> str:
    total = max(0, ms) // 1000
    return f"{total // 60:02d}:{total % 60:02d}"


def format_srt_timestamp(ms: int) -> str:
    value = max(0, ms)
    hours, remainder = divmod(value, 3_600_000)
    minutes, remainder = divmod(remainder, 60_000)
    seconds, milliseconds = divmod(remainder, 1000)
    return f"{hours:02d}:{minutes:02d}:{seconds:02d},{milliseconds:03d}"


def correction_status_text(report: dict[str, Any]) -> str:
    status = report.get("correctionStatus") or (
        "completed" if report.get("correctionModel") else "fallback"
    )
    elapsed_ms = int(report.get("correctionElapsedMs") or 0)
    elapsed = f"，耗时 {elapsed_ms / 1000:.1f} 秒" if elapsed_ms > 0 else ""
    model = report.get("correctionModel")
    model_text = f"，模型 {model}" if model else ""
    if status == "completed":
        return f"已完成{model_text}{elapsed}"
    if status == "partial":
        return f"部分完成{model_text}{elapsed}"
    if status == "timeout":
        return f"超时降级{elapsed}"
    if status == "pending":
        return "基础报告已可下载，全文纠偏生成中"
    if status == "skipped":
        return "未执行"
    return f"降级为实时译文{elapsed}"


def render_txt(report: dict[str, Any]) -> str:
    lines = [
        f"# {report['sessionName']}",
        (
            f"领域：{report['domain']}  |  语言：{report['sourceLanguage']} -> "
            f"{report['targetLanguage']}  |  时长：{report['durationText']}"
        ),
        f"生成时间：{report['generatedAt']}",
        f"全文纠偏：{correction_status_text(report)}",
        "",
        "【摘要】",
        report.get("summary", ""),
        "",
        "【双语终稿】",
    ]
    for segment in report["segments"]:
        lines.append(f"[{segment['timecode']}] {segment['sourceText']}")
        lines.append(f"          {segment['finalTranslation']}")
    revisions = report.get("finalRevisions", [])
    if revisions:
        lines += ["", "【会后校正记录】"]
        for revision in revisions:
            lines.append(
                f"- {revision['beforeText']}  =>  {revision['afterText']}  （{revision['reason']}）"
            )
    elif report.get("correctionStatus") == "completed":
        lines += ["", "【会后校正记录】", "全文纠偏已完成，本场未发现需要改写的译文。"]
    if report.get("qualityNotes"):
        lines += ["", "【质量说明】", report["qualityNotes"]]
    return "\n".join(lines)


def render_srt(report: dict[str, Any]) -> str:
    blocks = []
    for index, segment in enumerate(report["segments"], start=1):
        start = format_srt_timestamp(segment["startMs"])
        end_ms = (
            segment["endMs"]
            if segment["endMs"] > segment["startMs"]
            else segment["startMs"] + 2000
        )
        end = format_srt_timestamp(end_ms)
        blocks.append(
            f"{index}\n{start} --> {end}\n{segment['sourceText']}\n"
            f"{segment['finalTranslation']}\n"
        )
    return "\n".join(blocks)


def _escape_markdown_cell(value: str) -> str:
    return value.replace("|", "\\|")


def render_md(report: dict[str, Any]) -> str:
    markdown = [
        f"# {report['sessionName']}",
        "",
        f"- **领域**：{report['domain']}",
        f"- **语言**：{report['sourceLanguage']} → {report['targetLanguage']}",
        f"- **时长**：{report['durationText']}",
        (
            f"- **句数**：{report['metrics']['segments']}  ｜ **实时修正**："
            f"{report['metrics']['realtimeRevisions']}  ｜ **会后修正**："
            f"{report['metrics']['finalRevisions']}"
        ),
        f"- **生成时间**：{report['generatedAt']}",
        f"- **全文纠偏**：{correction_status_text(report)}",
        "",
        "## 摘要",
        report.get("summary", ""),
        "",
        "## 双语终稿",
        "",
        "| 时间 | 原文 | 终稿译文 |",
        "| --- | --- | --- |",
    ]
    for segment in report["segments"]:
        source = _escape_markdown_cell(segment["sourceText"])
        translation = _escape_markdown_cell(segment["finalTranslation"])
        markdown.append(f"| {segment['timecode']} | {source} | {translation} |")
    revisions = report.get("finalRevisions", [])
    if revisions:
        markdown += [
            "",
            "## 会后校正记录",
            "",
            "| 原译文 | 校正后 | 原因 |",
            "| --- | --- | --- |",
        ]
        for revision in revisions:
            markdown.append(
                f"| {_escape_markdown_cell(revision['beforeText'])} | "
                f"{_escape_markdown_cell(revision['afterText'])} | {revision['reason']} |"
            )
    elif report.get("correctionStatus") == "completed":
        markdown += ["", "## 会后校正记录", "", "全文纠偏已完成，本场未发现需要改写的译文。"]
    if report.get("qualityNotes"):
        markdown += ["", "## 质量说明", report["qualityNotes"]]
    return "\n".join(markdown)
