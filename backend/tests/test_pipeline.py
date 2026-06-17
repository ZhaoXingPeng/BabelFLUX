"""同传管线 / 纠偏 / 报告 的单元测试（不触网，用脚本化假 WebSocket）。

重点回归：译文比源滞后约 2.8s，常常跨越「下一句的 speech_started」才到达——
必须按 item_id（源）+ response_id（译文 FIFO 绑定）正确配对，绝不能张冠李戴。
"""

import asyncio
import base64
import json
from types import SimpleNamespace

import pytest

from app.core.config import settings
from app.services.pipeline import InterpretationPipeline
from app.services.providers.dashscope import DashScopeConfig, LiveTranslateSession
from app.services.report import generate_session_report, render_md, render_srt, render_txt
from app.services.revision import RealtimeReviser
from app.services.session_store import SegmentRecord, SessionRecord


class FakeWS:
    """脚本化假 WS：按顺序产出服务端消息（JSON 字符串）。"""

    def __init__(self, messages: list[dict]) -> None:
        self._messages = [json.dumps(m, ensure_ascii=False) for m in messages]
        self.sent: list[str] = []

    async def send(self, data: str) -> None:
        self.sent.append(data)

    async def close(self) -> None:
        return None

    def __aiter__(self) -> "FakeWS":
        self._iter = iter(self._messages)
        return self

    async def __anext__(self) -> str:
        try:
            await asyncio.sleep(0)
            return next(self._iter)
        except StopIteration as exc:
            raise StopAsyncIteration from exc


def _dummy_config() -> DashScopeConfig:
    return DashScopeConfig(api_key="sk-test", workspace_id="ws-test")


@pytest.mark.asyncio
async def test_lagged_translation_pairs_with_correct_source() -> None:
    # 两句话：A 的译文滞后到 B 的 speech_started 之后才到达。
    src_txt = "conversation.item.input_audio_transcription.text"
    src_done = "conversation.item.input_audio_transcription.completed"
    messages = [
        {"type": "session.created"},
        {"type": "input_audio_buffer.speech_started", "item_id": "itemA"},
        {"type": src_txt, "item_id": "itemA", "stash": "Hello"},
        {"type": src_done, "item_id": "itemA", "transcript": "Hello world."},
        # 下一句已经开始（B），但 A 的译文还没回来
        {"type": "input_audio_buffer.speech_started", "item_id": "itemB"},
        {"type": src_txt, "item_id": "itemB", "stash": "Goodbye"},
        # A 的译文现在才到（滞后，跨越了 B 的 speech_started）
        {"type": "response.created", "response": {"id": "resp1"}},
        {"type": "response.text.text", "response_id": "resp1", "text": "你好"},
        {"type": "response.text.done", "response_id": "resp1", "text": "你好，世界。"},
        {"type": "response.done", "response": {"id": "resp1"}},
        {"type": src_done, "item_id": "itemB", "transcript": "Goodbye world."},
        {"type": "response.created", "response": {"id": "resp2"}},
        {"type": "response.text.done", "response_id": "resp2", "text": "再见，世界。"},
        {"type": "response.done", "response": {"id": "resp2"}},
    ]
    record = SessionRecord(session_id="t", source_language="en", target_language="zh")
    events: list[dict] = []

    async def emit(ev: dict) -> None:
        events.append(ev)

    pipeline = InterpretationPipeline(settings=settings, record=record, emit=emit)
    pipeline._reviser.enabled = False  # 禁用 LLM 复核，避免触网

    session = LiveTranslateSession(
        _dummy_config(),
        model="m",
        websocket_connect=lambda *_a, **_k: _async_return(FakeWS(messages)),
    )
    await session.connect()
    await pipeline._consume(session)

    assert _source_text_for_item(record, "itemA") == "Hello world."
    # A 的译文配到 A，而非 B。
    assert _translation_text_for_response(record, "resp1") == "你好，世界。"
    assert _source_text_for_item(record, "itemB") == "Goodbye world."
    assert _translation_text_for_response(record, "resp2") == "再见，世界。"


async def _async_return(value: object) -> object:
    return value


def _source_text_for_item(record: SessionRecord, item_id: str) -> str:
    return " ".join(s.source_text for s in record.segments if s.item_id == item_id).strip()


def _translation_text_for_response(record: SessionRecord, response_id: str) -> str:
    return "".join(
        s.translation_text for s in record.segments if s.response_id == response_id
    ).strip()


@pytest.mark.asyncio
async def test_tts_audio_delta_emits_audio_segment_for_paired_response() -> None:
    audio_bytes = b"\x01\x02\x03\x04"
    messages = [
        {"type": "session.created"},
        {"type": "input_audio_buffer.speech_started", "item_id": "itemA"},
        {
            "type": "conversation.item.input_audio_transcription.completed",
            "item_id": "itemA",
            "transcript": "Hello world.",
        },
        {"type": "response.created", "response": {"id": "resp1"}},
        {"type": "response.text.done", "response_id": "resp1", "text": "你好，世界。"},
        {
            "type": "response.audio.delta",
            "response_id": "resp1",
            "delta": base64.b64encode(audio_bytes).decode("ascii"),
        },
    ]
    record = SessionRecord(
        session_id="tts-audio", source_language="en", target_language="zh", tts_enabled=True
    )
    events: list[dict] = []

    async def emit(ev: dict) -> None:
        events.append(ev)

    pipeline = InterpretationPipeline(settings=settings, record=record, emit=emit)
    pipeline._reviser.enabled = False

    session = LiveTranslateSession(
        _dummy_config(),
        model="m",
        tts_enabled=True,
        websocket_connect=lambda *_a, **_k: _async_return(FakeWS(messages)),
    )
    await session.connect()
    await pipeline._consume(session)

    audio_event = next(event for event in events if event["type"] == "audio_segment")
    assert audio_event == {
        "type": "audio_segment",
        "segmentId": record.segments[0].segment_id,
        "audioBase64": base64.b64encode(audio_bytes).decode("ascii"),
        "sampleRate": 24000,
    }


@pytest.mark.asyncio
async def test_tts_audio_delta_waits_until_response_is_paired() -> None:
    audio_bytes = b"\x05\x06"
    messages = [
        {"type": "session.created"},
        {"type": "input_audio_buffer.speech_started", "item_id": "itemA"},
        {
            "type": "conversation.item.input_audio_transcription.completed",
            "item_id": "itemA",
            "transcript": "Hello world.",
        },
        {"type": "response.created", "response": {"id": "resp1"}},
        {
            "type": "response.audio.delta",
            "response_id": "resp1",
            "delta": base64.b64encode(audio_bytes).decode("ascii"),
        },
        {"type": "response.text.done", "response_id": "resp1", "text": "你好，世界。"},
    ]
    record = SessionRecord(
        session_id="tts-audio-first", source_language="en", target_language="zh", tts_enabled=True
    )
    events: list[dict] = []

    async def emit(ev: dict) -> None:
        events.append(ev)

    pipeline = InterpretationPipeline(settings=settings, record=record, emit=emit)
    pipeline._reviser.enabled = False

    session = LiveTranslateSession(
        _dummy_config(),
        model="m",
        tts_enabled=True,
        websocket_connect=lambda *_a, **_k: _async_return(FakeWS(messages)),
    )
    await session.connect()
    await pipeline._consume(session)

    audio_event = next(event for event in events if event["type"] == "audio_segment")
    assert audio_event["segmentId"] == record.segments[0].segment_id
    assert audio_event["audioBase64"] == base64.b64encode(audio_bytes).decode("ascii")


@pytest.mark.asyncio
async def test_pipeline_pause_resume_gate_blocks_until_resumed() -> None:
    record = SessionRecord(session_id="pause-gate", source_language="en", target_language="zh")

    async def emit(_ev: dict) -> None:
        return None

    pipeline = InterpretationPipeline(settings=settings, record=record, emit=emit)
    pipeline.pause()
    task = asyncio.create_task(pipeline._wait_if_paused())
    await asyncio.sleep(0)

    assert not task.done()

    pipeline.resume()
    waited = await asyncio.wait_for(task, timeout=1)
    assert waited >= 0


@pytest.mark.asyncio
async def test_source_incremental_partials_are_accumulated() -> None:
    record = SessionRecord(session_id="partial-merge", source_language="en", target_language="zh")
    events: list[dict] = []

    async def emit(ev: dict) -> None:
        events.append(ev)

    pipeline = InterpretationPipeline(settings=settings, record=record, emit=emit)

    await pipeline._on_source("I feel so fortunate", "itemA", final=False)
    await pipeline._on_source("works, in fact,", "itemA", final=False)

    assert _source_text_for_item(record, "itemA") == "I feel so fortunate works, in fact,"

    await pipeline._on_source(
        "I feel so fortunate that one of the works, in fact, did not meet her mark.",
        "itemA",
        final=True,
    )

    assert (
        _source_text_for_item(record, "itemA")
        == "I feel so fortunate that one of the works, in fact, did not meet her mark."
    )
    assert events[-1]["segment"]["text"] == (
        "I feel so fortunate that one of the works, in fact, did not meet her mark."
    )


@pytest.mark.asyncio
async def test_source_snapshot_partials_do_not_duplicate_prefixes() -> None:
    record = SessionRecord(session_id="partial-dedupe", source_language="en", target_language="zh")

    async def emit(_ev: dict) -> None:
        return None

    pipeline = InterpretationPipeline(settings=settings, record=record, emit=emit)

    await pipeline._on_source("I feel so fortunate.", "itemA", final=False)
    await pipeline._on_source(
        "I feel so fortunate that my first job was working at the Museum of Modern Art,",
        "itemA",
        final=False,
    )

    item_a_text = _source_text_for_item(record, "itemA")
    assert item_a_text.startswith("I feel so fortunate that my first job")
    assert "I feel so fortunate. I feel so fortunate" not in item_a_text

    await pipeline._on_source(
        "I feel so fortunate that I feel so fortunate that my I feel so fortunate that my first.",
        "itemB",
        final=False,
    )

    assert _source_text_for_item(record, "itemB") == "I feel so fortunate that my first."


@pytest.mark.asyncio
async def test_short_noise_source_does_not_take_next_long_translation() -> None:
    record = SessionRecord(session_id="noise-source", source_language="en", target_language="zh")

    async def emit(_ev: dict) -> None:
        return None

    pipeline = InterpretationPipeline(settings=settings, record=record, emit=emit)

    pipeline._begin_segment("itemNoise")
    await pipeline._on_source("Olha.", "itemNoise", final=True)
    pipeline._begin_segment("itemA")
    await pipeline._on_source(
        "I I feel so fortunate that my first job was working at the Museum of Modern Art.",
        "itemA",
        final=True,
    )
    await pipeline._on_translation(
        "我感到非常幸运，我的第一份工作是在现代艺术博物馆。",
        "respA",
        final=True,
    )

    noise = next(segment for segment in record.segments if segment.item_id == "itemNoise")
    paired = next(segment for segment in record.segments if segment.item_id == "itemA")
    assert noise.translation_text == ""
    assert paired.source_text.startswith("I feel so fortunate")
    assert "I I feel" not in paired.source_text
    assert paired.translation_text == "我感到非常幸运，我的第一份工作是在现代艺术博物馆。"


@pytest.mark.asyncio
async def test_source_sliding_window_partials_are_overlap_merged() -> None:
    record = SessionRecord(session_id="partial-overlap", source_language="en", target_language="zh")

    async def emit(_ev: dict) -> None:
        return None

    pipeline = InterpretationPipeline(settings=settings, record=record, emit=emit)

    for text in [
        "the Museum of Modern Art",
        "Museum of Modern Art on",
        "of Modern Art on a",
        "Modern Art on a retrospective",
        "Art on a retrospective of",
        "on a retrospective of painter Elizabeth Murray.",
    ]:
        await pipeline._on_source(text, "itemA", final=False)

    assert record.segments[0].source_text == (
        "the Museum of Modern Art on a retrospective of painter Elizabeth Murray."
    )


@pytest.mark.asyncio
async def test_source_partials_drop_unstable_tail_before_overlap_merge() -> None:
    record = SessionRecord(
        session_id="partial-unstable-tail", source_language="en", target_language="zh"
    )

    async def emit(_ev: dict) -> None:
        return None

    pipeline = InterpretationPipeline(settings=settings, record=record, emit=emit)

    await pipeline._on_source("She told me that a few didn", "itemA", final=False)
    await pipeline._on_source("that a few didn't quite meet her", "itemA", final=False)
    await pipeline._on_source("meet her own mark", "itemA", final=False)

    assert record.segments[0].source_text == (
        "She told me that a few didn't quite meet her own mark"
    )


@pytest.mark.asyncio
async def test_source_partials_merge_contraction_stashes_without_duplicates() -> None:
    record = SessionRecord(
        session_id="partial-contraction-stash", source_language="en", target_language="zh"
    )

    async def emit(_ev: dict) -> None:
        return None

    pipeline = InterpretationPipeline(settings=settings, record=record, emit=emit)

    await pipeline._on_source("She told me that a few didn't quite meet her", "itemA", final=False)
    await pipeline._on_source("'t quite meet her own mark", "itemA", final=False)
    await pipeline._on_source("what we're always celebrating is", "itemA", final=False)
    await pipeline._on_source(
        "'re always celebrating is creativity and mastery.", "itemA", final=False
    )

    text = record.segments[0].source_text
    assert "didn't quite meet her 't quite meet her" not in text
    assert "we're always celebrating is 're always celebrating" not in text
    assert "She told me that a few didn't quite meet her own mark" in text
    assert "what we're always celebrating is creativity and mastery." in text


@pytest.mark.asyncio
async def test_display_segments_keep_source_and_translation_paired() -> None:
    record = SessionRecord(
        session_id="target-clause-split", source_language="en", target_language="zh"
    )

    async def emit(_ev: dict) -> None:
        return None

    pipeline = InterpretationPipeline(settings=settings, record=record, emit=emit)

    await pipeline._on_source(
        (
            "I feel so fortunate that my first job was working at the Museum of Modern Art. "
            "I learned so much from her."
        ),
        "itemA",
        final=False,
    )
    await pipeline._on_translation(
        "我感到非常幸运，我的第一份工作是在现代艺术博物馆。 我从她身上学到了很多。",
        "responseA",
        final=False,
    )

    assert len(record.segments) == 2
    assert record.segments[0].source_text == (
        "I feel so fortunate that my first job was working at the Museum of Modern Art."
    )
    assert record.segments[0].translation_text == (
        "我感到非常幸运，我的第一份工作是在现代艺术博物馆。"
    )
    assert record.segments[0].status == "final"
    assert record.segments[1].source_text == "I learned so much from her."
    assert record.segments[1].translation_text == "我从她身上学到了很多。"
    assert record.segments[1].status == "partial"
    assert max(segment.end_ms for segment in record.segments) <= 1000

    pipeline.elapsed_ms = 20_000
    await pipeline._on_source(
        (
            "I feel so fortunate that my first job was working at the Museum of Modern Art. "
            "I learned so much from her."
        ),
        "itemA",
        final=True,
    )
    await pipeline._on_translation(
        "我感到非常幸运，我的第一份工作是在现代艺术博物馆。 我从她身上学到了很多。",
        "responseA",
        final=True,
    )

    assert len(record.segments) == 2
    assert record.segments[0].source_text == (
        "I feel so fortunate that my first job was working at the Museum of Modern Art."
    )
    assert record.segments[0].translation_text == (
        "我感到非常幸运，我的第一份工作是在现代艺术博物馆。"
    )
    assert record.segments[1].source_text == "I learned so much from her."
    assert record.segments[1].translation_text == "我从她身上学到了很多。"
    assert record.segments[0].end_ms == record.segments[1].start_ms
    assert record.segments[0].end_ms < record.segments[1].end_ms


@pytest.mark.asyncio
async def test_display_segments_split_mismatched_sentence_counts_for_readability() -> None:
    record = SessionRecord(session_id="paired-tail", source_language="en", target_language="zh")

    async def emit(_ev: dict) -> None:
        return None

    pipeline = InterpretationPipeline(settings=settings, record=record, emit=emit)

    await pipeline._on_source(
        "First sentence. Second sentence. Third sentence.",
        "itemA",
        final=True,
    )
    await pipeline._on_translation("第一句。第二句。", "responseA", final=True)

    assert len(record.segments) == 2
    assert record.segments[0].source_text == "First sentence."
    assert record.segments[0].translation_text == "第一句。"
    assert record.segments[1].source_text == "Second sentence. Third sentence."
    assert record.segments[1].translation_text == "第二句。"


@pytest.mark.asyncio
async def test_long_live_translate_turn_is_split_into_readable_display_segments() -> None:
    record = SessionRecord(session_id="long-turn", source_language="en", target_language="zh")

    async def emit(_ev: dict) -> None:
        return None

    pipeline = InterpretationPipeline(settings=settings, record=record, emit=emit)
    pipeline._begin_segment("itemA")
    pipeline.elapsed_ms = 34_000

    await pipeline._on_source(
        (
            "One of the works, in fact, so didn't meet her mark, she had set it out in the "
            "trash in her studio, and her neighbor had taken it because she saw its value."
        ),
        "itemA",
        final=True,
    )
    await pipeline._on_translation(
        (
            "事实上，其中一件作品甚至远未达到她的标准，以至于她把它扔进了工作室的垃圾桶，"
            "结果被邻居捡走了，因为邻居看出了它的价值。"
        ),
        "responseA",
        final=True,
    )

    assert len(record.segments) >= 3
    assert all(len(segment.source_text) < 150 for segment in record.segments)
    assert all(len(segment.translation_text) < 80 for segment in record.segments)
    assert all(
        later.start_ms - earlier.start_ms < 10_000
        for earlier, later in zip(record.segments, record.segments[1:], strict=False)
    )


@pytest.mark.asyncio
async def test_semantic_source_continuations_merge_before_translation_binding() -> None:
    record = SessionRecord(
        session_id="semantic-continuation", source_language="en", target_language="zh"
    )

    async def emit(_ev: dict) -> None:
        return None

    pipeline = InterpretationPipeline(settings=settings, record=record, emit=emit)
    pipeline.elapsed_ms = 10_000
    pipeline._begin_segment("itemA")
    await pipeline._on_source(
        "She told me that a few didn't quite meet her own mark",
        "itemA",
        final=True,
    )

    pipeline.elapsed_ms = 10_300
    pipeline._begin_segment("itemB")
    await pipeline._on_source(
        "For what she wanted them to be one of the works,",
        "itemB",
        final=True,
    )

    pipeline.elapsed_ms = 10_600
    pipeline._begin_segment("itemC")
    await pipeline._on_source("In fact so didn't meet her mark,", "itemC", final=True)

    assert len(record.segments) == 1
    assert record.segments[0].source_text == (
        "She told me that a few didn't quite meet her own mark "
        "For what she wanted them to be one of the works, "
        "In fact so didn't meet her mark,"
    )


@pytest.mark.asyncio
async def test_final_display_bounds_split_long_time_span_under_ten_seconds() -> None:
    record = SessionRecord(session_id="long-span", source_language="en", target_language="zh")

    async def emit(_ev: dict) -> None:
        return None

    pipeline = InterpretationPipeline(settings=settings, record=record, emit=emit)
    pipeline._begin_segment("itemA")
    pipeline.elapsed_ms = 34_000

    await pipeline._on_source(
        (
            "I realized that success is a moment, but what we're always celebrating is "
            "creativity and mastery. But this is the thing: what gets us to convert "
            "success into mastery?"
        ),
        "itemA",
        final=True,
    )
    await pipeline._on_translation(
        "我意识到成功只是一瞬间，而我们真正持续庆祝的是创造力与精进。但关键在于，是什么让我们将一时的成功转化为持久的精进？",
        "responseA",
        final=True,
    )

    assert len(record.segments) >= 4
    assert all(segment.end_ms - segment.start_ms <= 10_000 for segment in record.segments)
    assert all(segment.source_text for segment in record.segments)
    assert all(segment.translation_text for segment in record.segments)


@pytest.mark.asyncio
async def test_cjk_repetition_is_collapsed_for_source_and_translation() -> None:
    record = SessionRecord(session_id="cjk-repeat", source_language="en", target_language="zh")

    async def emit(_ev: dict) -> None:
        return None

    pipeline = InterpretationPipeline(settings=settings, record=record, emit=emit)

    await pipeline._on_source(
        "从最黑暗的深处走来从最黑暗的深处走来，黑暗的深处走来，一个举刀，一个举刀对致命微笑。",
        "itemA",
        final=True,
    )
    await pipeline._on_translation(
        "从最黑暗的深处走来，从最黑暗的深处走来，黑暗的深处走来。",
        "responseA",
        final=True,
    )

    combined_source = "".join(segment.source_text for segment in record.segments)
    combined_translation = "".join(segment.translation_text for segment in record.segments)
    assert "从最黑暗的深处走来从最黑暗的深处走来" not in combined_source
    assert "，黑暗的深处走来" not in combined_source
    assert "一个举刀，一个举刀对" not in combined_source
    assert "从最黑暗的深处走来，从最黑暗的深处走来" not in combined_translation


@pytest.mark.asyncio
async def test_cjk_sliding_window_partials_are_overlap_merged() -> None:
    record = SessionRecord(session_id="cjk-overlap", source_language="zh", target_language="en")

    async def emit(_ev: dict) -> None:
        return None

    pipeline = InterpretationPipeline(settings=settings, record=record, emit=emit)

    for text in [
        "从最黑暗的深处走来",
        "最黑暗的深处走来，致命的微笑",
        "深处走来，致命的微笑也来了",
        "致命的微笑也来了，到处都是三头鹰",
    ]:
        await pipeline._on_source(text, "itemA", final=False)

    combined_source = "".join(segment.source_text for segment in record.segments)
    assert "从最黑暗的深处走来最黑暗的深处走来" not in combined_source
    assert "致命的微笑也来了" in combined_source
    assert combined_source.endswith("到处都是三头鹰")


@pytest.mark.asyncio
async def test_cjk_anchored_partials_replace_unstable_tail() -> None:
    record = SessionRecord(session_id="cjk-anchor", source_language="zh", target_language="en")

    async def emit(_ev: dict) -> None:
        return None

    pipeline = InterpretationPipeline(settings=settings, record=record, emit=emit)

    for text in [
        "大家好，我的职业是一名英语辅导老师。我的学",
        "辅导老师。我的学生主要是中学生。",
        "前段时间一节课上，一个学生。",
        "上，一个学生告诉我他们年。",
        "他们学生告诉我，他们年级有一位同学常。",
        "年级有一位同学长期睡眠不足。",
        "为了长期睡眠不足，为了做作业，每晚只能睡四五个小时。",
    ]:
        await pipeline._on_source(text, "itemA", final=False)

    combined_source = "".join(segment.source_text for segment in record.segments)
    assert "辅导老师。我的学。辅导老师" not in combined_source
    assert "上，一个学生。上，一个学生" not in combined_source
    assert "他们年。他们学生" not in combined_source
    assert "长期睡眠不足。为了长期睡眠不足" not in combined_source
    assert "大家好，我的职业是一名英语辅导老师。我的学生主要是中学生。" in combined_source
    assert "每晚只能睡四五个小时" in combined_source


@pytest.mark.asyncio
async def test_chinese_source_to_english_translation_keeps_spaces_and_splits_readably() -> None:
    record = SessionRecord(session_id="zh-to-en", source_language="zh", target_language="en")

    async def emit(_ev: dict) -> None:
        return None

    pipeline = InterpretationPipeline(settings=settings, record=record, emit=emit)
    pipeline.elapsed_ms = 43_000

    await pipeline._on_source(
        "如果他们的作业完全按质按量去完成的话，至少需要五个半小时。这样算下来，即便是毫不间断地做，也要做到十二点。",
        "itemA",
        final=True,
    )
    await pipeline._on_translation(
        (
            "If their homework is completed with both quality and quantity, it takes at "
            "least five and a half hours. Calculated this way, even if they work without "
            "any break, they still have to work until midnight."
        ),
        "responseA",
        final=True,
    )

    combined_translation = " ".join(segment.translation_text for segment in record.segments)
    assert "completed with both quality" in combined_translation
    assert "completedwithbothquality" not in combined_translation
    assert len(record.segments) >= 2
    assert all(len(segment.source_text) <= 60 for segment in record.segments)
    assert all(segment.translation_text for segment in record.segments)


@pytest.mark.asyncio
async def test_english_target_keeps_spaces_when_translation_contains_cjk_noise() -> None:
    record = SessionRecord(session_id="en-target-mixed", source_language="zh", target_language="en")

    async def emit(_ev: dict) -> None:
        return None

    pipeline = InterpretationPipeline(settings=settings, record=record, emit=emit)

    await pipeline._on_source(
        "这是关于现代艺术博物馆的一段说明。",
        "itemA",
        final=True,
    )
    await pipeline._on_translation(
        "This is a note about the Museum of Modern Art 中文 note.",
        "responseA",
        final=True,
    )

    combined_translation = " ".join(segment.translation_text for segment in record.segments)
    assert "Museum of Modern Art" in combined_translation
    assert "MuseumofModernArt" not in combined_translation
    assert "This is a note" in combined_translation


@pytest.mark.asyncio
async def test_chinese_target_preserves_embedded_english_term_spacing() -> None:
    record = SessionRecord(session_id="zh-target-mixed", source_language="en", target_language="zh")

    async def emit(_ev: dict) -> None:
        return None

    pipeline = InterpretationPipeline(settings=settings, record=record, emit=emit)

    await pipeline._on_source(
        "The talk references the Museum of Modern Art and Elizabeth Murray.",
        "itemA",
        final=True,
    )
    await pipeline._on_translation(
        "这段演讲提到了 Museum of Modern Art 和 Elizabeth Murray。",
        "responseA",
        final=True,
    )

    combined_translation = "".join(segment.translation_text for segment in record.segments)
    assert "Museum of Modern Art" in combined_translation
    assert "MuseumofModernArt" not in combined_translation
    assert "Elizabeth Murray" in combined_translation


@pytest.mark.asyncio
async def test_wrong_manual_source_language_does_not_glue_english_output() -> None:
    record = SessionRecord(
        session_id="wrong-source-language", source_language="zh", target_language="en"
    )

    async def emit(_ev: dict) -> None:
        return None

    pipeline = InterpretationPipeline(settings=settings, record=record, emit=emit)

    await pipeline._on_source(
        "I feel so fortunate that my first job was working at the Museum of Modern Art.",
        "itemA",
        final=True,
    )
    await pipeline._on_translation(
        "I feel so fortunate that my first job was working at the Museum of Modern Art 中文.",
        "responseA",
        final=True,
    )

    combined_source = " ".join(segment.source_text for segment in record.segments)
    combined_translation = " ".join(segment.translation_text for segment in record.segments)
    assert "I feel so fortunate" in combined_source
    assert "Museum of Modern Art" in combined_translation
    assert "MuseumofModernArt" not in combined_translation


@pytest.mark.asyncio
async def test_auto_source_language_flips_same_target_english_to_chinese() -> None:
    record = SessionRecord(
        session_id="auto-source-flip", source_language="auto", target_language="en"
    )

    async def emit(_ev: dict) -> None:
        return None

    pipeline = InterpretationPipeline(settings=settings, record=record, emit=emit)

    await pipeline._on_source(
        "I feel so fortunate that my first job was working at the Museum of Modern Art.",
        "itemA",
        final=False,
    )

    assert record.source_language == "en"
    assert record.target_language == "zh"


def test_auto_source_initial_provider_language_uses_opposite_target_hint() -> None:
    zh_target = SessionRecord(session_id="auto-zh", source_language="auto", target_language="zh")
    en_target = SessionRecord(session_id="auto-en", source_language="auto", target_language="en")

    async def emit(_ev: dict) -> None:
        return None

    assert (
        InterpretationPipeline(settings=settings, record=zh_target, emit=emit)
        ._initial_provider_source_language()
        == "en"
    )
    assert (
        InterpretationPipeline(settings=settings, record=en_target, emit=emit)
        ._initial_provider_source_language()
        == "zh"
    )


@pytest.mark.asyncio
async def test_auto_pcm_preflight_replays_prefix_and_flips_same_language_target() -> None:
    record = SessionRecord(session_id="auto-pcm", source_language="auto", target_language="en")

    async def emit(_ev: dict) -> None:
        return None

    pipeline = InterpretationPipeline(settings=settings, record=record, emit=emit)

    async def fake_detect(audio: bytes) -> None:
        assert audio == b"a" + b"b"
        pipeline._lock_language_pair("en")

    pipeline._detect_language_from_pcm = fake_detect  # type: ignore[method-assign]
    queue: asyncio.Queue[bytes | None] = asyncio.Queue()
    await queue.put(b"a")
    await queue.put(b"b")
    await queue.put(None)

    frames, ended = await pipeline._preflight_pcm_language(queue)

    assert frames == [b"a", b"b"]
    assert ended is True
    assert record.source_language == "en"
    assert record.target_language == "zh"


@pytest.mark.asyncio
async def test_lowercase_source_continuation_does_not_shift_following_translations() -> None:
    record = SessionRecord(
        session_id="continuation-source", source_language="en", target_language="zh"
    )

    async def emit(_ev: dict) -> None:
        return None

    pipeline = InterpretationPipeline(settings=settings, record=record, emit=emit)

    pipeline._begin_segment("itemA")
    await pipeline._on_source(
        (
            "One of the works, in fact, so didn't meet her mark, "
            "she had set it out in the trash on her."
        ),
        "itemA",
        final=True,
    )
    await pipeline._on_translation(
        "事实上，其中一件作品甚至远未达到她的标准，她把它扔进了工作室的垃圾桶，结果被邻居捡走了，因为邻居看出了它的价值。",
        "respA",
        final=True,
    )

    pipeline._begin_segment("itemB")
    await pipeline._on_source(
        "the trash in her studio, and her neighbor had taken it because she saw its value.",
        "itemB",
        final=True,
    )

    pipeline._begin_segment("itemC")
    await pipeline._on_source(
        "In that moment, my view of success and creativity changed.",
        "itemC",
        final=True,
    )
    await pipeline._on_translation(
        "在那一刻，我对成功和创造力的看法发生了改变。",
        "respB",
        final=True,
    )

    item_a_segments = [segment for segment in record.segments if segment.item_id == "itemA"]
    item_c_segments = [segment for segment in record.segments if segment.item_id == "itemC"]
    combined_item_a_source = " ".join(segment.source_text for segment in item_a_segments)

    assert len(record.segments) >= 3
    assert "the trash in her studio" in combined_item_a_source
    assert "on her. the trash" not in combined_item_a_source
    assert len(item_c_segments) == 1
    assert item_c_segments[0].source_text == (
        "In that moment, my view of success and creativity changed."
    )
    assert item_c_segments[0].translation_text == "在那一刻，我对成功和创造力的看法发生了改变。"


@pytest.mark.asyncio
async def test_partial_display_segments_do_not_collapse_after_split() -> None:
    record = SessionRecord(
        session_id="partial-display-stable", source_language="en", target_language="zh"
    )

    async def emit(_ev: dict) -> None:
        return None

    pipeline = InterpretationPipeline(settings=settings, record=record, emit=emit)

    await pipeline._on_source("First sentence. Second sentence.", "itemA", final=False)
    await pipeline._on_translation("第一句。第二句。", "responseA", final=False)

    assert len(record.segments) == 2
    assert record.segments[0].translation_text == "第一句。"
    assert record.segments[1].translation_text == "第二句。"

    await pipeline._on_translation("第一句第二句。", "responseA", final=False)

    assert len(record.segments) == 2
    assert record.segments[0].translation_text == "第一句。"
    assert record.segments[1].translation_text == "第二句。"


@pytest.mark.asyncio
async def test_partial_display_bounds_stay_under_one_second_when_split() -> None:
    record = SessionRecord(
        session_id="partial-low-latency", source_language="en", target_language="zh"
    )

    async def emit(_ev: dict) -> None:
        return None

    pipeline = InterpretationPipeline(settings=settings, record=record, emit=emit)

    await pipeline._on_source(
        "I feel so fortunate that my first job was working at the Museum of Modern Art.",
        "itemA",
        final=False,
    )

    assert len(record.segments) == 1
    assert max(segment.end_ms for segment in record.segments) <= 1000


@pytest.mark.asyncio
async def test_final_display_timing_does_not_drift_when_same_text_repeats() -> None:
    record = SessionRecord(session_id="stable-final", source_language="en", target_language="zh")
    events: list[dict] = []

    async def emit(ev: dict) -> None:
        events.append(ev)

    pipeline = InterpretationPipeline(settings=settings, record=record, emit=emit)
    text = "One two three four five six seven eight nine ten eleven twelve."

    pipeline.elapsed_ms = 3_000
    await pipeline._on_source(text, "itemA", final=True)
    first_timing = [(segment.start_ms, segment.end_ms) for segment in record.segments]
    first_event_count = len(events)

    pipeline.elapsed_ms = 10_000
    await pipeline._on_source(text, "itemA", final=True)

    assert [(segment.start_ms, segment.end_ms) for segment in record.segments] == first_timing
    assert len(events) == first_event_count


def test_revision_parser_filters_low_confidence_and_unchanged() -> None:
    reviser = RealtimeReviser(
        client=None, model="m", source_language="en", target_language="zh", domain="通用"
    )
    window = [
        SegmentRecord(segment_id="s1", index=1, source_text="A", translation_text="旧译文"),
        SegmentRecord(segment_id="s2", index=2, source_text="B", translation_text="最新句"),
    ]
    content = json.dumps(
        {
            "revisions": [
                {"segmentId": "s1", "afterText": "新译文", "reason": "术语", "confidence": 0.9},
                {"segmentId": "s1", "afterText": "低分", "reason": "x", "confidence": 0.2},
                {"segmentId": "s2", "afterText": "改最新句", "reason": "x", "confidence": 0.9},
                {"segmentId": "s1", "afterText": "旧译文", "reason": "无变化", "confidence": 0.9},
            ]
        }
    )
    out = reviser._parse(content, revisable_ids={"s1"}, window=window)
    assert len(out) == 1
    assert out[0]["segmentId"] == "s1"
    assert out[0]["afterText"] == "新译文"
    assert out[0]["beforeText"] == "旧译文"


def _sample_report() -> dict:
    return {
        "reportId": "r1",
        "sessionName": "测试报告",
        "domain": "通用",
        "sourceLanguage": "en",
        "targetLanguage": "zh",
        "durationText": "01:23",
        "generatedAt": "2026-06-06 10:00:00",
        "summary": "摘要内容",
        "qualityNotes": "质量说明",
        "metrics": {"segments": 1, "realtimeRevisions": 0, "finalRevisions": 1},
        "segments": [
            {
                "segmentId": "s1",
                "startMs": 0,
                "endMs": 4000,
                "timecode": "00:00",
                "sourceText": "Hello world",
                "liveTranslation": "你好世界",
                "finalTranslation": "你好，世界",
                "revisedRealtime": False,
            }
        ],
        "finalRevisions": [
            {
                "segmentId": "s1",
                "beforeText": "你好世界",
                "afterText": "你好，世界",
                "reason": "标点",
            }
        ],
    }


def test_report_renderers_produce_expected_formats() -> None:
    report = _sample_report()
    txt = render_txt(report)
    assert "测试报告" in txt and "你好，世界" in txt and "会后校正记录" in txt

    srt = render_srt(report)
    assert "00:00:00,000 --> 00:00:04,000" in srt
    assert "Hello world" in srt and "你好，世界" in srt

    md = render_md(report)
    assert md.startswith("# 测试报告")
    assert "| 时间 | 原文 | 终稿译文 |" in md


@pytest.mark.asyncio
async def test_report_counts_partial_segments_created_before_stop() -> None:
    record = SessionRecord(session_id="report-partial", source_language="en", target_language="zh")
    seg = record.get_or_create_segment("s1", 1)
    seg.start_ms = 2000
    seg.end_ms = 5000
    seg.source_text = "I feel so fortunate."
    seg.translation_text = "我感到非常幸运。"
    seg.status = "partial"

    report = await generate_session_report(record, settings=settings, client=None)

    assert report["metrics"]["segments"] == 1
    assert report["durationText"] == "00:05"
    assert report["segments"][0]["sourceText"] == "I feel so fortunate."


@pytest.mark.asyncio
async def test_report_skips_source_only_segments() -> None:
    record = SessionRecord(
        session_id="report-source-only", source_language="en", target_language="zh"
    )
    translated = record.get_or_create_segment("s1", 1)
    translated.start_ms = 0
    translated.end_ms = 3000
    translated.source_text = "Translated source."
    translated.translation_text = "已有译文。"
    translated.status = "final"
    source_only = record.get_or_create_segment("s2", 2)
    source_only.start_ms = 4000
    source_only.end_ms = 6000
    source_only.source_text = "Source without translation."
    source_only.status = "final"

    report = await generate_session_report(record, settings=settings, client=None)

    assert report["metrics"]["segments"] == 1
    assert [segment["segmentId"] for segment in report["segments"]] == ["s1"]
    assert "Source without translation." not in render_txt(report)


@pytest.mark.asyncio
async def test_report_generation_uses_final_correction_output() -> None:
    class CorrectionClient:
        async def generate(self, **_: object) -> object:
            return SimpleNamespace(
                content=json.dumps(
                    {
                        "summary": "完整纠偏摘要",
                        "qualityNotes": "译文整体准确，已统一标点。",
                        "glossaryHits": [],
                        "segments": [{"id": "s1", "finalTranslation": "你好，世界。"}],
                        "revisions": [
                            {
                                "id": "s1",
                                "before": "你好世界",
                                "after": "你好，世界。",
                                "reason": "补充标点",
                            }
                        ],
                    },
                    ensure_ascii=False,
                )
            )

    record = SessionRecord(
        session_id="report-correction", source_language="en", target_language="zh"
    )
    seg = record.get_or_create_segment("s1", 1)
    seg.start_ms = 0
    seg.end_ms = 3000
    seg.source_text = "Hello world."
    seg.translation_text = "你好世界"
    seg.status = "final"

    original_provider = settings.model_provider
    original_key = settings.dashscope_api_key
    object.__setattr__(settings, "model_provider", "real")
    object.__setattr__(settings, "dashscope_api_key", "sk-test")
    try:
        report = await generate_session_report(
            record,
            settings=settings,
            client=CorrectionClient(),  # type: ignore[arg-type]
        )
    finally:
        object.__setattr__(settings, "model_provider", original_provider)
        object.__setattr__(settings, "dashscope_api_key", original_key)

    assert report["correctionStatus"] == "completed"
    assert report["correctionModel"] == settings.final_correction_model
    assert report["metrics"]["finalRevisions"] == 1
    assert report["segments"][0]["finalTranslation"] == "你好，世界。"
    assert report["summary"] == "完整纠偏摘要"
    txt = render_txt(report)
    assert "全文纠偏：已完成" in txt
    assert "会后校正记录" in txt
    assert "补充标点" in txt


@pytest.mark.asyncio
async def test_report_generation_can_emit_pending_base_report_without_waiting() -> None:
    class SlowCorrectionClient:
        async def generate(self, **_: object) -> object:
            await asyncio.sleep(1)
            return object()

    record = SessionRecord(session_id="report-pending", source_language="en", target_language="zh")
    seg = record.get_or_create_segment("s1", 1)
    seg.start_ms = 0
    seg.end_ms = 3000
    seg.source_text = "Hello world."
    seg.translation_text = "live translation"
    seg.status = "final"

    started = asyncio.get_running_loop().time()
    report = await generate_session_report(
        record,
        settings=settings,
        client=SlowCorrectionClient(),  # type: ignore[arg-type]
        run_final_correction=False,
        pending_final_correction=True,
    )
    elapsed = asyncio.get_running_loop().time() - started

    assert elapsed < 0.5
    assert report["correctionStatus"] == "pending"
    assert report["metrics"]["segments"] == 1
    assert report["segments"][0]["finalTranslation"] == "live translation"
    assert "Hello world." in render_srt(report)


@pytest.mark.asyncio
async def test_report_generation_falls_back_when_final_correction_times_out() -> None:
    class SlowCorrectionClient:
        async def generate(self, **_: object) -> object:
            await asyncio.sleep(1)
            return object()

    record = SessionRecord(session_id="report-timeout", source_language="en", target_language="zh")
    seg = record.get_or_create_segment("s1", 1)
    seg.start_ms = 0
    seg.end_ms = 3000
    seg.source_text = "Hello world."
    seg.translation_text = "你好，世界。"
    seg.status = "final"

    original_provider = settings.model_provider
    original_key = settings.dashscope_api_key
    original_timeout = settings.final_correction_timeout_seconds
    object.__setattr__(settings, "model_provider", "real")
    object.__setattr__(settings, "dashscope_api_key", "sk-test")
    object.__setattr__(settings, "final_correction_timeout_seconds", 0.01)
    try:
        started = asyncio.get_running_loop().time()
        report = await generate_session_report(
            record,
            settings=settings,
            client=SlowCorrectionClient(),  # type: ignore[arg-type]
        )
        elapsed = asyncio.get_running_loop().time() - started
    finally:
        object.__setattr__(settings, "model_provider", original_provider)
        object.__setattr__(settings, "dashscope_api_key", original_key)
        object.__setattr__(settings, "final_correction_timeout_seconds", original_timeout)

    assert elapsed < 0.5
    assert report["correctionModel"] is None
    assert report["correctionStatus"] == "timeout"
    assert "超过" in report["correctionError"]
    assert report["metrics"]["segments"] == 1
    assert report["segments"][0]["finalTranslation"] == "你好，世界。"
