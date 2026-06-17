"""会后完整纠偏 + 会话报告。

同传结束后，把整场的「原文 + 实时译文」连同领域策略与术语表交给较强的文本
大模型（默认 qwen-plus，可换 deepseek-v4-pro / qwen3.7-plus），做一次全局校正：
统一术语、修正实时阶段来不及纠正的错误、产出双语终稿与摘要。结果可渲染为
TXT / SRT / Markdown / JSON 供前端下载。

LLM 失败时优雅降级：直接用实时译文拼出报告，保证「结束→可下载」始终可用。
"""

from __future__ import annotations

import asyncio
import json
import time
from typing import Any
from uuid import uuid4

from app.core.config import Settings
from app.services.providers.dashscope import DashScopeClient
from app.services.revision import domain_focus
from app.services.session_store import SessionRecord


def build_final_correction_prompt(
    domain: str, source_language: str, target_language: str, glossary_block: str
) -> str:
    return "\n".join(
        [
            "你是 BabelFlux / 巴别流 同传的「会后完整纠偏」模块，对整场传译做最终全局校正。",
            f"领域：{domain}；源语言：{source_language}；目标语言：{target_language}。",
            f"领域策略：{domain_focus(domain)}",
            "输入是整场按时间排序的句子（含 id、原文、实时译文）。请：",
            "1. 通读全文，利用完整上下文统一术语、修正实时阶段的错误（误译/术语漂移/人名数字否定）。",  # noqa: E501
            "2. 为每一句给出最终校正译文 finalTranslation（即使无需改动也要给出，与原译相同即可）。",  # noqa: E501
            "3. 列出确实发生改动的句子到 revisions（before=实时译文，after=最终译文，reason=简短原因）。",  # noqa: E501
            "4. 给出全场中文摘要 summary 与质量说明 qualityNotes。",
            "硬性规则：忠实原意、不扩写、不臆造；术语表优先；保持口语可读。",
            "术语表：",
            glossary_block or "（无）",
            "仅输出 JSON：{\"summary\":\"...\",\"qualityNotes\":\"...\","
            "\"glossaryHits\":[{\"term\":\"...\",\"translation\":\"...\"}],"
            "\"segments\":[{\"id\":\"...\",\"finalTranslation\":\"...\"}],"
            "\"revisions\":[{\"id\":\"...\",\"before\":\"...\",\"after\":\"...\",\"reason\":\"...\"}]}。",
        ]
    )


def _glossary_block(glossary: list[dict[str, Any]]) -> str:
    lines = []
    for t in sorted(glossary, key=lambda x: x.get("priority", 0), reverse=True):
        src, tgt = t.get("sourceTerm"), t.get("targetTerm")
        if src and tgt:
            note = f"；备注：{t['note']}" if t.get("note") else ""
            lines.append(f"- {src} -> {tgt}{note}")
    return "\n".join(lines)


def _fmt_ts(ms: int) -> str:
    total = max(0, ms) // 1000
    return f"{total // 60:02d}:{total % 60:02d}"


def _fmt_srt_ts(ms: int) -> str:
    ms = max(0, ms)
    h, rem = divmod(ms, 3_600_000)
    m, rem = divmod(rem, 60_000)
    s, msec = divmod(rem, 1000)
    return f"{h:02d}:{m:02d}:{s:02d},{msec:03d}"


async def generate_session_report(
    record: SessionRecord,
    *,
    settings: Settings,
    client: DashScopeClient | None,
    report_id: str | None = None,
    run_final_correction: bool = True,
    pending_final_correction: bool = False,
) -> dict[str, Any]:
    segments = record.reportable_segments()
    report_id = report_id or f"{record.session_id}-report-{uuid4().hex[:8]}"

    llm_out: dict[str, Any] = {}
    correction_status = "skipped"
    correction_error = ""
    correction_elapsed_ms = 0
    if not segments:
        correction_error = "本场无有效转写与译文，未执行会后完整纠偏。"
    elif pending_final_correction:
        correction_status = "pending"
        correction_error = "基础报告已可下载，会后完整纠偏正在后台生成。"
    elif client is None or not settings.use_real_pipeline:
        correction_error = "未启用真实模型，报告使用实时译文生成。"
    elif run_final_correction:
        timeout_seconds = max(0.1, settings.final_correction_timeout_seconds)
        started = time.perf_counter()
        try:
            llm_out = await asyncio.wait_for(
                _call_correction_llm(record, segments, settings, client),
                timeout=timeout_seconds,
            )
            correction_elapsed_ms = int((time.perf_counter() - started) * 1000)
            expected_ids, returned_ids = _correction_segment_coverage(llm_out, segments)
            if expected_ids.issubset(returned_ids):
                correction_status = "completed"
            elif returned_ids:
                correction_status = "partial"
                missing = len(expected_ids - returned_ids)
                correction_error = f"会后完整纠偏返回缺少 {missing} 句，缺失句已使用实时译文。"
            else:
                correction_status = "fallback"
                correction_error = "会后完整纠偏未返回可用句级终稿，报告使用实时译文生成。"
        except TimeoutError:
            correction_elapsed_ms = int((time.perf_counter() - started) * 1000)
            correction_status = "timeout"
            correction_error = (
                f"会后完整纠偏超过 {timeout_seconds:.0f} 秒未完成，报告使用实时译文生成。"
            )
            llm_out = {}
        except Exception as exc:  # noqa: BLE001 - 报告仍需可下载，但必须暴露纠偏失败原因。
            correction_elapsed_ms = int((time.perf_counter() - started) * 1000)
            correction_status = "fallback"
            correction_error = (
                "会后完整纠偏调用失败，报告使用实时译文生成。"
                f"原因：{type(exc).__name__}: {exc}"
            )
            llm_out = {}

    # 防御：真实 LLM 偶尔会把 segments/revisions 返回成非 dict（如字符串列表）。
    # 这些项必须忽略而非崩溃——否则整份报告生成失败（此处在降级 try 之外）。
    final_by_id = {
        s["id"]: s.get("finalTranslation", "")
        for s in llm_out.get("segments", [])
        if isinstance(s, dict) and s.get("id")
    }
    llm_revisions = {
        r.get("id"): r
        for r in llm_out.get("revisions", [])
        if isinstance(r, dict) and r.get("id")
    }

    duration_ms = max(
        record.duration_ms,
        max((seg.end_ms or seg.start_ms for seg in segments), default=0),
    )
    report_segments: list[dict[str, Any]] = []
    final_revisions: list[dict[str, Any]] = []
    for seg in segments:
        live = seg.translation_text
        final_translation = (final_by_id.get(seg.segment_id) or live).strip() or live
        report_segments.append(
            {
                "segmentId": seg.segment_id,
                "startMs": seg.start_ms,
                "endMs": seg.end_ms or seg.start_ms,
                "timecode": _fmt_ts(seg.start_ms),
                "sourceText": seg.source_text,
                "liveTranslation": live,
                "finalTranslation": final_translation,
                "revisedRealtime": seg.revised,
            }
        )
        if final_translation != live:
            rev = llm_revisions.get(seg.segment_id, {})
            final_revisions.append(
                {
                    "segmentId": seg.segment_id,
                    "beforeText": live,
                    "afterText": final_translation,
                    "reason": rev.get("reason") or "会后全局校正",
                }
            )

    # 实时阶段已发生的修正也并入修正记录展示
    realtime_revisions = [
        {
            "segmentId": r.target_segment_ids[0] if r.target_segment_ids else "",
            "beforeText": r.before_text,
            "afterText": r.after_text,
            "reason": r.reason,
            "stage": "实时",
        }
        for r in record.revisions
    ]

    report = {
        "reportId": report_id,
        "sessionId": record.session_id,
        "sessionName": record.session_name,
        "domain": record.domain,
        "sourceLanguage": record.source_language,
        "targetLanguage": record.target_language,
        "durationMs": duration_ms,
        "durationText": _fmt_ts(duration_ms),
        "generatedAt": time.strftime("%Y-%m-%d %H:%M:%S"),
        "summary": llm_out.get("summary", "") or _fallback_summary(segments),
        "qualityNotes": llm_out.get("qualityNotes", "") or correction_error,
        "glossaryHits": llm_out.get("glossaryHits", []),
        "metrics": {
            "segments": len(report_segments),
            "realtimeRevisions": len(record.revisions),
            "finalRevisions": len(final_revisions),
            "durationText": _fmt_ts(duration_ms),
        },
        "segments": report_segments,
        "finalRevisions": final_revisions,
        "realtimeRevisions": realtime_revisions,
        "correctionModel": settings.final_correction_model if llm_out else None,
        "correctionStatus": correction_status,
        "correctionError": correction_error,
        "correctionElapsedMs": correction_elapsed_ms,
    }
    record.report = report
    return report


async def _call_correction_llm(
    record: SessionRecord,
    segments: list[Any],
    settings: Settings,
    client: DashScopeClient,
) -> dict[str, Any]:
    glossary_block = _glossary_block(record.glossary)
    system = build_final_correction_prompt(
        record.domain, record.source_language, record.target_language, glossary_block
    )
    lines = [
        f"[{s.segment_id}] ({_fmt_ts(s.start_ms)}) 原文: {s.source_text}\n        实时译文: {s.translation_text}"  # noqa: E501
        for s in segments
    ]
    user = "整场句子如下：\n" + "\n".join(lines)
    result = await client.generate(
        model=settings.final_correction_model,
        endpoint="text",
        messages=[
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        parameters={"result_format": "message", "temperature": 0.2},
    )
    parsed = _loads_json(result.content)
    if parsed is None:
        raise ValueError("最终纠偏模型未返回可解析 JSON")
    return parsed


def _correction_segment_coverage(
    llm_out: dict[str, Any], segments: list[Any]
) -> tuple[set[str], set[str]]:
    expected_ids = {str(seg.segment_id) for seg in segments if getattr(seg, "segment_id", None)}
    returned_ids = {
        str(item.get("id"))
        for item in llm_out.get("segments", [])
        if isinstance(item, dict) and item.get("id") and item.get("finalTranslation") is not None
    }
    return expected_ids, returned_ids


def _fallback_summary(segments: list[Any]) -> str:
    if not segments:
        return "本场无有效转写内容。"
    return f"本场共 {len(segments)} 句，已完成实时转写与翻译。"


def _loads_json(content: str) -> dict[str, Any] | None:
    content = (content or "").strip()
    if content.startswith("```"):
        content = content.strip("`")
        if content.lower().startswith("json"):
            content = content[4:]
    start, end = content.find("{"), content.rfind("}")
    if start == -1 or end == -1 or end < start:
        return None
    try:
        return json.loads(content[start : end + 1])
    except (ValueError, TypeError):
        return None


# ---------- 渲染 ----------
def _correction_status_text(report: dict[str, Any]) -> str:
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
        f"领域：{report['domain']}  |  语言：{report['sourceLanguage']} -> {report['targetLanguage']}"  # noqa: E501
        f"  |  时长：{report['durationText']}",
        f"生成时间：{report['generatedAt']}",
        f"全文纠偏：{_correction_status_text(report)}",
        "",
        "【摘要】",
        report.get("summary", ""),
        "",
        "【双语终稿】",
    ]
    for seg in report["segments"]:
        lines.append(f"[{seg['timecode']}] {seg['sourceText']}")
        lines.append(f"          {seg['finalTranslation']}")
    revisions = report.get("finalRevisions", [])
    if revisions:
        lines += ["", "【会后校正记录】"]
        for r in revisions:
            lines.append(f"- {r['beforeText']}  =>  {r['afterText']}  （{r['reason']}）")
    elif report.get("correctionStatus") == "completed":
        lines += ["", "【会后校正记录】", "全文纠偏已完成，本场未发现需要改写的译文。"]
    if report.get("qualityNotes"):
        lines += ["", "【质量说明】", report["qualityNotes"]]
    return "\n".join(lines)


def render_srt(report: dict[str, Any]) -> str:
    blocks = []
    for i, seg in enumerate(report["segments"], start=1):
        start = _fmt_srt_ts(seg["startMs"])
        end = _fmt_srt_ts(seg["endMs"] if seg["endMs"] > seg["startMs"] else seg["startMs"] + 2000)
        blocks.append(f"{i}\n{start} --> {end}\n{seg['sourceText']}\n{seg['finalTranslation']}\n")
    return "\n".join(blocks)


def render_md(report: dict[str, Any]) -> str:
    md = [
        f"# {report['sessionName']}",
        "",
        f"- **领域**：{report['domain']}",
        f"- **语言**：{report['sourceLanguage']} → {report['targetLanguage']}",
        f"- **时长**：{report['durationText']}",
        f"- **句数**：{report['metrics']['segments']}  ｜ **实时修正**："
        f"{report['metrics']['realtimeRevisions']}  ｜ **会后修正**：{report['metrics']['finalRevisions']}",  # noqa: E501
        f"- **生成时间**：{report['generatedAt']}",
        f"- **全文纠偏**：{_correction_status_text(report)}",
        "",
        "## 摘要",
        report.get("summary", ""),
        "",
        "## 双语终稿",
        "",
        "| 时间 | 原文 | 终稿译文 |",
        "| --- | --- | --- |",
    ]
    for seg in report["segments"]:
        src = seg["sourceText"].replace("|", "\\|")
        tgt = seg["finalTranslation"].replace("|", "\\|")
        md.append(f"| {seg['timecode']} | {src} | {tgt} |")
    revisions = report.get("finalRevisions", [])
    if revisions:
        md += ["", "## 会后校正记录", "", "| 原译文 | 校正后 | 原因 |", "| --- | --- | --- |"]
        for r in revisions:
            md.append(
                f"| {r['beforeText'].replace('|', chr(92) + '|')} | "
                f"{r['afterText'].replace('|', chr(92) + '|')} | {r['reason']} |"
            )
    elif report.get("correctionStatus") == "completed":
        md += ["", "## 会后校正记录", "", "全文纠偏已完成，本场未发现需要改写的译文。"]
    if report.get("qualityNotes"):
        md += ["", "## 质量说明", report["qualityNotes"]]
    return "\n".join(md)
