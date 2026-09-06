from app.services.report_rendering import (
    correction_status_text,
    format_srt_timestamp,
    format_timecode,
    render_md,
    render_srt,
    render_txt,
)


def _report() -> dict[str, object]:
    return {
        "sessionName": "演示报告",
        "domain": "技术",
        "sourceLanguage": "en",
        "targetLanguage": "zh",
        "durationText": "00:04",
        "generatedAt": "2026-09-07 10:00:00",
        "correctionStatus": "completed",
        "correctionModel": "qwen-plus",
        "correctionElapsedMs": 1200,
        "summary": "摘要",
        "qualityNotes": "质量说明",
        "metrics": {"segments": 1, "realtimeRevisions": 0, "finalRevisions": 0},
        "segments": [
            {
                "timecode": "00:00",
                "startMs": 0,
                "endMs": 0,
                "sourceText": "source | text",
                "finalTranslation": "译文 | text",
            }
        ],
        "finalRevisions": [],
    }


def test_report_rendering_formats_and_clamps_timestamps() -> None:
    assert format_timecode(-1) == "00:00"
    assert format_timecode(61_000) == "01:01"
    assert format_srt_timestamp(-1) == "00:00:00,000"
    assert format_srt_timestamp(3_661_234) == "01:01:01,234"
    assert correction_status_text(_report()) == "已完成，模型 qwen-plus，耗时 1.2 秒"


def test_report_renderers_preserve_srt_minimum_duration_and_markdown_escaping() -> None:
    report = _report()

    srt = render_srt(report)
    markdown = render_md(report)
    text = render_txt(report)

    assert "00:00:00,000 --> 00:00:02,000" in srt
    assert "source \\| text" in markdown
    assert "译文 \\| text" in markdown
    assert "【双语终稿】" in text
    assert report["segments"][0]["sourceText"] == "source | text"
