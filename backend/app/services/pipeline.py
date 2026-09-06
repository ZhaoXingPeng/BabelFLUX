"""同传管线编排。

把媒体解码（services.media）+ LiveTranslate 实时会话（providers.dashscope.realtime）
+ 实时纠偏（services.revision）编排为统一的前后端 WebSocket 事件流：
    session_started / source_sync_state / transcript_segment / translation_segment
    / revision_event / session_report / error
所有段落与修正同时写入 session_store，供会后完整纠偏与报告下载使用。

两种音频入口：
    run_media(source)       — 后端从本地文件/在线 URL 解码并按实时节奏喂入。
    run_pcm_stream(queue)   — 前端采集（麦克风/标签页/系统音频）经 WS 二进制流喂入。
"""

from __future__ import annotations

import asyncio
import base64
import re
import time
from collections.abc import Awaitable, Callable
from contextlib import aclosing
from typing import Any
from uuid import uuid4

from app.core.config import Settings
from app.models.events import AudioSegment, RevisionEvent, SourceSyncState, SubtitleSegment
from app.services.display_planner import build_display_plan
from app.services.display_text import contains_cjk, normalize_display_text
from app.services.language_policy import (
    infer_source_language,
    initial_provider_source_language,
    opposite_language,
    should_preflight_language,
    suggest_language_pair,
)
from app.services.media import iter_pcm_frames
from app.services.model_selection import ModelSelection, select_model_profile
from app.services.providers.dashscope import (
    DashScopeClient,
    DashScopeConfig,
    LiveTranslateSession,
)
from app.services.revision import RealtimeReviser
from app.services.session_store import RevisionRecord, SegmentRecord, SessionRecord
from app.services.source_text import (
    collapse_adjacent_source_duplicates,
    normalize_source_word,
    normalize_source_words,
)

Emit = Callable[[dict[str, Any]], Awaitable[None]]

PARTIAL_THROTTLE_S = 0.08
MEDIA_PROGRESS_SYNC_S = 0.5
STOP_DRAIN_GRACE_S = 0.8
STOP_DRAIN_MAX_S = 3.0
DRAIN_GRACE_S = 4.0
DRAIN_MAX_S = 30.0
SYNC_EMIT_INTERVAL_S = 0.25
SYNC_LAG_WARN_MS = 600
SOURCE_MAX_WORDS_PER_DISPLAY_SEGMENT = 18
SOURCE_MAX_CJK_CHARS_PER_DISPLAY_SEGMENT = 28
TARGET_MAX_CHARS_PER_DISPLAY_SEGMENT = 28
TARGET_MAX_WORDS_PER_DISPLAY_SEGMENT = 18
CJK_LANGUAGE_PREFIXES = ("zh", "ja", "ko", "yue")
SOURCE_CONTINUATION_MAX_GAP_MS = 700
SOURCE_CONTINUATION_MAX_DURATION_MS = 12_000
SOURCE_CONTINUATION_MAX_CHARS = 180
TTS_OUTPUT_SAMPLE_RATE = 24000
PREFLIGHT_AUDIO_MS = 2000
PREFLIGHT_FRAME_MS = 40
PREFLIGHT_MAX_WAIT_S = 4.0

ENGLISH_SHORT_SOURCE_WORDS = {
    "a",
    "ah",
    "am",
    "an",
    "and",
    "are",
    "as",
    "at",
    "be",
    "but",
    "by",
    "go",
    "he",
    "hi",
    "i",
    "if",
    "in",
    "is",
    "it",
    "me",
    "my",
    "no",
    "of",
    "oh",
    "ok",
    "on",
    "or",
    "she",
    "so",
    "the",
    "to",
    "uh",
    "um",
    "up",
    "us",
    "we",
    "yes",
    "you",
}

SOURCE_CONTINUATION_PREFIXES = (
    "and ",
    "as ",
    "because ",
    "but ",
    "for ",
    "if ",
    "in fact",
    "of ",
    "or ",
    "so ",
    "that ",
    "then ",
    "to ",
    "which ",
    "while ",
    "who ",
    "whose ",
    "with ",
)


class InterpretationPipeline:
    def __init__(
        self,
        *,
        settings: Settings,
        record: SessionRecord,
        emit: Emit,
        websocket_connect: Callable[..., Any] | None = None,
    ) -> None:
        self.settings = settings
        self.record = record
        self.emit = emit
        self._config = DashScopeConfig.from_settings(settings)
        self._llm_client = DashScopeClient(self._config)
        self._model_selection: ModelSelection = select_model_profile(record.model_profile, settings)
        self._ws_connect = websocket_connect
        self._reviser = RealtimeReviser(
            client=self._llm_client,
            model=self._model_selection.realtime_revision_model,
            source_language=record.source_language,
            target_language=record.target_language,
            domain=record.domain,
        )
        self.elapsed_ms = 0
        self._seg_index = 0
        self._current: SegmentRecord | None = None
        self._roots: list[SegmentRecord] = []
        self._by_item: dict[str, SegmentRecord] = {}
        self._by_response: dict[str, SegmentRecord] = {}
        self._children_by_root: dict[str, list[SegmentRecord]] = {}
        self._display_count_by_root: dict[str, int] = {}
        self._raw_source_by_root: dict[str, str] = {}
        self._raw_translation_by_root: dict[str, str] = {}
        self._pending_audio_by_response: dict[str, list[bytes]] = {}
        self._continuation_items: set[str] = set()
        self._noise_roots: set[str] = set()
        self._source_final_roots: set[str] = set()
        self._translation_final_roots: set[str] = set()
        self._display_final_roots: set[str] = set()
        self._last_partial_emit: dict[str, float] = {}
        self._last_emitted_segment: dict[str, tuple[str, str, int, int]] = {}
        self._tts_sample_rate = TTS_OUTPUT_SAMPLE_RATE
        self._last_event_at = time.monotonic()
        self._last_sync_emit_at = 0.0
        self._client_playback_ms: int | None = None
        self._client_sent_audio_ms: int | None = None
        self._last_media_progress_sync_at = 0.0
        self._review_tasks: set[asyncio.Task[Any]] = set()
        self._session_finished = False
        self._language_alignment_checked = False
        self._session: LiveTranslateSession | None = None
        self._glossary_phrases = {
            str(t.get("sourceTerm")): str(t.get("targetTerm"))
            for t in record.glossary
            if t.get("sourceTerm") and t.get("targetTerm")
        }
        self._stopped = False
        self._pause_event = asyncio.Event()
        self._pause_event.set()

    # ---------- 对外入口 ----------
    async def run_media(self, source: str) -> None:
        self.record.status = "running"
        await self._preflight_media_language(source)
        await self._emit_sync("syncing", 0, "正在连接同传引擎…")
        session = LiveTranslateSession(
            self._config,
            model=self._model_selection.live_translate_model,
            source_language=self._initial_provider_source_language(),
            target_language=self.record.target_language,
            asr_model=self._model_selection.live_translate_asr_model,
            tts_enabled=self.record.tts_enabled,
            voice=self.settings.tts_voice,
            glossary=self._glossary_phrases or None,
            websocket_connect=self._ws_connect,
        )
        self._session = session
        await session.connect()
        consumer = asyncio.create_task(self._consume(session))
        try:
            await self._emit_sync("syncing", 0, "同传进行中")
            frames = iter_pcm_frames(
                source,
                realtime=True,
                on_progress=self._on_progress,
                pause_wait=self._wait_if_paused,
            )
            async with aclosing(frames) as stream:
                async for frame in stream:
                    if self._stopped:
                        break
                    await session.feed(frame)
                    await self._maybe_emit_media_progress()
            await session.feed_silence(2.5)
            await session.finish()
            await self._drain(consumer)
        finally:
            consumer.cancel()
            await session.close()
            self._session = None
            await self._await_reviews()
        self.record.duration_ms = self.elapsed_ms

    async def run_pcm_stream(self, queue: asyncio.Queue[bytes | None]) -> None:
        """前端采集音频经 WS 二进制流喂入；queue 收到 None 表示结束。"""
        self.record.status = "running"
        await self._emit_sync("ready", 0, "同传引擎就绪，等待音频播放")
        prefix_frames, prefix_ended = await self._preflight_pcm_language(queue)
        if self._stopped:
            return
        await self._emit_sync("syncing", 0, "正在连接同传引擎…")
        session = LiveTranslateSession(
            self._config,
            model=self._model_selection.live_translate_model,
            source_language=self._initial_provider_source_language(),
            target_language=self.record.target_language,
            asr_model=self._model_selection.live_translate_asr_model,
            tts_enabled=self.record.tts_enabled,
            voice=self.settings.tts_voice,
            glossary=self._glossary_phrases or None,
            websocket_connect=self._ws_connect,
        )
        self._session = session
        await session.connect()
        consumer = asyncio.create_task(self._consume(session))
        try:
            await self._emit_sync("syncing", 0, "同传进行中")
            for frame in prefix_frames:
                if self._stopped:
                    break
                self._on_progress(self.elapsed_ms + int(len(frame) / 2 / 16000 * 1000))
                await session.feed(frame)
                await self._emit_client_clock_sync_if_due()
            while not self._stopped and not prefix_ended:
                await self._wait_if_paused()
                frame = await queue.get()
                if frame is None:
                    break
                await self._wait_if_paused()
                self._on_progress(self.elapsed_ms + int(len(frame) / 2 / 16000 * 1000))
                await session.feed(frame)
                await self._emit_client_clock_sync_if_due()
            await session.feed_silence(2.0)
            await session.finish()
            await self._drain(consumer)
        finally:
            consumer.cancel()
            await session.close()
            self._session = None
            await self._await_reviews()
        self.record.duration_ms = self.elapsed_ms

    def stop(self) -> None:
        self._stopped = True
        self._pause_event.set()

    def pause(self) -> None:
        self._pause_event.clear()

    def resume(self) -> None:
        self._pause_event.set()

    def update_client_clock(self, playback_ms: int, sent_audio_ms: int) -> None:
        self._client_playback_ms = max(0, playback_ms)
        self._client_sent_audio_ms = max(0, sent_audio_ms)

    # ---------- 内部 ----------
    def _initial_provider_source_language(self) -> str:
        return initial_provider_source_language(
            self.record.source_language,
            self.record.target_language,
        )

    async def _preflight_media_language(self, source: str) -> None:
        if not self._should_preflight_language():
            return
        await self._emit_sync("syncing", 0, "正在自动检测源语言…")
        sample = bytearray()
        needed = int(16000 * 2 * PREFLIGHT_AUDIO_MS / 1000)
        frames = iter_pcm_frames(source, realtime=False, frame_ms=PREFLIGHT_FRAME_MS)
        async with aclosing(frames) as stream:
            async for frame in stream:
                sample.extend(frame)
                if len(sample) >= needed:
                    break
        if sample:
            await self._detect_language_from_pcm(bytes(sample))

    async def _preflight_pcm_language(
        self,
        queue: asyncio.Queue[bytes | None],
    ) -> tuple[list[bytes], bool]:
        if not self._should_preflight_language():
            return [], False
        await self._emit_sync("ready", 0, "正在自动检测源语言")
        frames: list[bytes] = []
        total_ms = 0
        ended = False
        deadline = time.monotonic() + PREFLIGHT_MAX_WAIT_S
        while not self._stopped and total_ms < PREFLIGHT_AUDIO_MS:
            timeout = max(0.05, deadline - time.monotonic())
            try:
                frame = await asyncio.wait_for(queue.get(), timeout=timeout)
            except TimeoutError:
                break
            if frame is None:
                ended = True
                break
            frames.append(frame)
            total_ms += int(len(frame) / 2 / 16000 * 1000)
        sample = b"".join(frames)
        if sample:
            await self._detect_language_from_pcm(sample)
        return frames, ended

    def _should_preflight_language(self) -> bool:
        return should_preflight_language(self.record.source_language, self.record.target_language)

    async def _detect_language_from_pcm(self, audio: bytes) -> None:
        if not audio:
            return
        source_hint = self._initial_provider_source_language()
        session = LiveTranslateSession(
            self._config,
            model=self._model_selection.live_translate_model,
            source_language=source_hint,
            target_language=self.record.target_language,
            asr_model=self._model_selection.live_translate_asr_model,
            tts_enabled=False,
            voice=self.settings.tts_voice,
            glossary=self._glossary_phrases or None,
            websocket_connect=self._ws_connect,
        )
        source_snapshots: list[str] = []
        try:
            await session.connect()
            await session.feed(audio)
            await session.feed_silence(1.0)
            await session.finish()
            events = session.events()
            deadline = time.monotonic() + PREFLIGHT_MAX_WAIT_S
            while time.monotonic() < deadline:
                timeout = max(0.05, deadline - time.monotonic())
                try:
                    ev = await asyncio.wait_for(anext(events), timeout=timeout)
                except (TimeoutError, StopAsyncIteration):
                    break
                if ev.kind in {"source_partial", "source_final"} and ev.text:
                    source_snapshots.append(ev.text)
                    inferred = self._infer_source_language(" ".join(source_snapshots[-3:]))
                    if inferred is not None:
                        self._lock_language_pair(inferred)
                        break
                if ev.kind in {"session_finished", "error"}:
                    break
        except Exception:  # noqa: BLE001 - 预检失败不阻塞主链路
            return
        finally:
            await session.close()

    async def _wait_if_paused(self) -> float:
        if self._pause_event.is_set():
            return 0.0
        started = time.monotonic()
        await self._pause_event.wait()
        return time.monotonic() - started

    def _on_progress(self, produced_ms: int) -> None:
        self.elapsed_ms = produced_ms

    async def _maybe_emit_media_progress(self, *, force: bool = False) -> None:
        now = time.monotonic()
        if not force and now - self._last_media_progress_sync_at < MEDIA_PROGRESS_SYNC_S:
            return
        self._last_media_progress_sync_at = now
        await self._emit_sync("syncing", 0, "同传进行中", source_ms=self.elapsed_ms)

    async def _consume(self, session: LiveTranslateSession) -> None:
        try:
            async for ev in session.events():
                self._last_event_at = time.monotonic()
                await self._handle(ev)
        except asyncio.CancelledError:
            raise
        except Exception as exc:  # noqa: BLE001 - 把底层错误上抛为前端 error 事件
            await self._emit_error(f"同传引擎异常：{exc}")

    async def _drain(self, consumer: asyncio.Task[Any]) -> None:
        """音频喂完后，等待最后若干句的最终事件落定。"""
        max_wait = STOP_DRAIN_MAX_S if self._stopped else DRAIN_MAX_S
        grace = STOP_DRAIN_GRACE_S if self._stopped else DRAIN_GRACE_S
        deadline = time.monotonic() + max_wait
        while time.monotonic() < deadline:
            if self._session_finished:
                break
            if consumer.done():
                break
            if time.monotonic() - self._last_event_at > grace:
                break
            await asyncio.sleep(0.3)

    async def _handle(self, ev: Any) -> None:
        kind = ev.kind
        if kind == "speech_started":
            self._begin_segment(ev.item_id)
        elif kind == "session_finished":
            self._session_finished = True
        elif kind == "source_partial":
            await self._on_source(ev.text, ev.item_id, final=False)
        elif kind == "source_final":
            await self._on_source(ev.text, ev.item_id, final=True)
        elif kind == "response_created":
            return
        elif kind == "translation_partial":
            await self._on_translation(ev.text, ev.response_id, final=False)
        elif kind == "translation_final":
            seg = await self._on_translation(ev.text, ev.response_id, final=True)
            if seg is not None:
                await self._on_segment_complete(seg)
        elif kind == "audio":
            await self._on_audio(ev)
        elif kind == "error":
            await self._emit_error(ev.text)

    # 源用输入 item_id 归段；译文用 response_id 按 FIFO 绑定到最早未配译文的段，
    # 从而抵抗「译文比源滞后 ~2.8s、跨越下一句 speech_started」带来的错配。
    def _begin_segment(self, item_id: str | None = None) -> SegmentRecord:
        self._seg_index += 1
        seg_id = f"{self.record.session_id}-seg-{self._seg_index}"
        seg = self.record.get_or_create_segment(seg_id, self._seg_index)
        seg.start_ms = self.elapsed_ms
        seg.item_id = item_id
        self._roots.append(seg)
        self._children_by_root[seg.segment_id] = [seg]
        if item_id:
            self._by_item[item_id] = seg
        self._current = seg
        return seg

    def _source_segment(self, item_id: str | None) -> SegmentRecord:
        if item_id:
            seg = self._by_item.get(item_id)
            return seg if seg is not None else self._begin_segment(item_id)
        if self._current is not None:
            return self._current
        return self._begin_segment(None)

    def _bind_response(self, response_id: str | None, translation_text: str = "") -> SegmentRecord:
        if response_id and response_id in self._by_response:
            return self._by_response[response_id]
        # 绑定到最早一个尚未分配 response 的模型根段（FIFO，与生成顺序一致）。
        for seg in self._roots:
            if seg.response_id is not None or seg.segment_id in self._noise_roots:
                continue
            if self._should_skip_response_root(seg, translation_text):
                self._noise_roots.add(seg.segment_id)
                continue
            seg.response_id = response_id
            if response_id:
                self._by_response[response_id] = seg
            self._sync_child_response_ids(seg)
            return seg
        seg = self._begin_segment(None)
        seg.response_id = response_id
        if response_id:
            self._by_response[response_id] = seg
        self._sync_child_response_ids(seg)
        return seg

    def _should_skip_response_root(self, seg: SegmentRecord, translation_text: str) -> bool:
        if seg.translation_text or not seg.source_text:
            return False
        if not self._has_later_unbound_source_root(seg):
            return False
        if len(translation_text.strip()) < 6:
            return False
        return self._looks_like_noise_source(seg.source_text)

    def _has_later_unbound_source_root(self, seg: SegmentRecord) -> bool:
        try:
            index = self._roots.index(seg)
        except ValueError:
            return False
        return any(
            root.response_id is None
            and root.segment_id not in self._noise_roots
            and bool(root.source_text or self._raw_source_by_root.get(root.segment_id))
            for root in self._roots[index + 1 :]
        )

    def _looks_like_noise_source(self, text: str) -> bool:
        words = self._normalize_source_words(text.split())
        words = [word for word in words if word]
        if len(words) != 1:
            return False
        word = words[0]
        if self.record.source_language.lower().startswith("en"):
            return word not in ENGLISH_SHORT_SOURCE_WORDS
        return len(word) <= 4

    def _sync_child_response_ids(self, root: SegmentRecord) -> None:
        for child in self._children_by_root.get(root.segment_id, [root]):
            child.response_id = root.response_id

    def _merge_source_continuation_if_needed(
        self, seg: SegmentRecord, item_id: str | None, text: str
    ) -> SegmentRecord:
        if item_id in self._continuation_items:
            return self._by_item.get(item_id) or seg
        if (
            not item_id
            or seg.source_text
            or seg.translation_text
            or seg.response_id is not None
            or not (
                self._looks_like_source_continuation(text)
                or self._should_merge_source_root_with_previous(seg, item_id, text, final=True)
            )
        ):
            return seg

        previous = self._previous_source_root(seg)
        if previous is None:
            return seg

        self._continuation_items.add(item_id)
        self._by_item[item_id] = previous
        self._discard_empty_root(seg)
        return previous

    def _previous_source_root(self, seg: SegmentRecord) -> SegmentRecord | None:
        try:
            index = self._roots.index(seg)
        except ValueError:
            index = len(self._roots)
        for root in reversed(self._roots[:index]):
            if root.source_text or self._raw_source_by_root.get(root.segment_id):
                return root
        return None

    def _discard_empty_root(self, seg: SegmentRecord) -> None:
        if seg.source_text or seg.translation_text or seg.response_id is not None:
            return
        if seg in self._roots:
            self._roots.remove(seg)
        if self._current is seg:
            self._current = self._roots[-1] if self._roots else None
        self._children_by_root.pop(seg.segment_id, None)
        self._display_count_by_root.pop(seg.segment_id, None)
        self._raw_source_by_root.pop(seg.segment_id, None)
        self._raw_translation_by_root.pop(seg.segment_id, None)
        self._source_final_roots.discard(seg.segment_id)
        self._translation_final_roots.discard(seg.segment_id)
        self._display_final_roots.discard(seg.segment_id)
        if seg.response_id:
            self._pending_audio_by_response.pop(seg.response_id, None)
        self.record._by_id.pop(seg.segment_id, None)
        self.record.segments = [
            existing for existing in self.record.segments if existing.segment_id != seg.segment_id
        ]

    def _looks_like_source_continuation(self, text: str) -> bool:
        value = text.strip()
        if not value:
            return False
        if value[0] in {"'", "\u2019"}:
            return True
        match = re.search(r"[A-Za-z]", value)
        return bool(match and value[match.start()].islower())

    def _should_merge_source_root_with_previous(
        self, seg: SegmentRecord, item_id: str | None, text: str, *, final: bool
    ) -> bool:
        if (
            not final
            or not item_id
            or seg.source_text
            or seg.translation_text
            or seg.response_id is not None
        ):
            return False
        previous = self._previous_source_root(seg)
        if previous is None:
            return False
        if previous.response_id is not None or previous.translation_text:
            return False
        previous_text = self._raw_source_by_root.get(previous.segment_id, previous.source_text)
        if not previous_text.strip() or self._has_terminal_source_punctuation(previous_text):
            return False
        gap_ms = seg.start_ms - previous.end_ms
        if gap_ms > SOURCE_CONTINUATION_MAX_GAP_MS:
            return False
        merged_duration = max(seg.end_ms, self.elapsed_ms, seg.start_ms) - previous.start_ms
        if merged_duration > SOURCE_CONTINUATION_MAX_DURATION_MS:
            return False
        merged_text = f"{previous_text} {text}".strip()
        if len(merged_text) > SOURCE_CONTINUATION_MAX_CHARS:
            return False
        return self._starts_with_source_continuation_cue(text)

    def _starts_with_source_continuation_cue(self, text: str) -> bool:
        value = re.sub(r"\s+", " ", text.strip()).lower().lstrip("\"'“‘")
        if not value:
            return False
        if value[0] in {"'", "\u2019"}:
            return True
        if self._starts_with_lowercase_alpha(value):
            return True
        return value.startswith(SOURCE_CONTINUATION_PREFIXES)

    def _has_terminal_source_punctuation(self, text: str) -> bool:
        return text.rstrip().endswith((".", "!", "?", "。", "！", "？"))

    def _merge_source_partial(self, previous: str, text: str) -> str:
        current = text.strip()
        if not current:
            return previous
        prior = previous.strip()
        if not prior:
            return self._collapse_source_repetition(current)

        if current in prior or prior.endswith(current):
            return prior

        cjk_overlapped = self._merge_cjk_overlap(prior, current)
        if cjk_overlapped is not None:
            return self._collapse_source_repetition(cjk_overlapped)

        # DashScope ASR partials can be either full snapshots or small incremental stashes.
        # Keep snapshots as-is, but append true incremental fragments so the UI never
        # regresses from a complete prefix to a trailing phrase such as "works, in fact,".
        normalized_prior = prior.rstrip(" .!?。！？")
        if current.startswith(normalized_prior) or len(current) > len(prior) * 1.2:
            return self._prefer_source_snapshot(prior, current)

        overlapped = self._merge_source_overlap(prior, current)
        if overlapped is not None:
            return self._collapse_source_repetition(overlapped)

        common_len = 0
        for prior_char, current_char in zip(prior, current, strict=False):
            if prior_char.lower() != current_char.lower():
                break
            common_len += 1
        # If two partials share a meaningful beginning, the newer one is usually a
        # corrected snapshot rather than a delta. Prefer it to avoid duplicated prefixes.
        if common_len >= 12:
            return self._prefer_source_snapshot(prior, current)

        no_space_before = current[0] in ",.;:!?，。；：！？)]}”’"
        if self._starts_with_lowercase_alpha(current) and prior[-1] in ".!?":
            prior = prior.rstrip(".!?") + ","
        separator = "" if prior[-1].isspace() or no_space_before else " "
        return self._collapse_source_repetition(f"{prior}{separator}{current}")

    def _starts_with_lowercase_alpha(self, text: str) -> bool:
        match = re.search(r"[A-Za-z]", text)
        return bool(match and text[match.start()].islower())

    def _merge_source_overlap(self, prior: str, current: str) -> str | None:
        prior_words = prior.split()
        current_words = current.split()
        if len(prior_words) < 2 or len(current_words) < 2:
            return None
        prior_norm = self._normalize_source_words(prior_words)
        current_variants = [current_words]
        trimmed_current = self._drop_unstable_source_prefix(current_words)
        if trimmed_current != current_words and len(trimmed_current) >= 2:
            current_variants.append(trimmed_current)
        for dropped_tail in range(min(3, len(prior_words) - 1) + 1):
            if dropped_tail and not all(
                self._looks_unstable_source_word(word) for word in prior_words[-dropped_tail:]
            ):
                continue
            base_words = (
                prior_words[: len(prior_words) - dropped_tail]
                if dropped_tail
                else prior_words
            )
            base_norm = prior_norm[: len(base_words)]
            for candidate_words in current_variants:
                current_norm = self._normalize_source_words(candidate_words)
                for size in range(min(len(base_words), len(candidate_words)), 1, -1):
                    if base_norm[-size:] == current_norm[:size]:
                        return " ".join([*base_words[:-size], *candidate_words])
        return None

    def _merge_cjk_overlap(self, prior: str, current: str) -> str | None:
        if not (self._contains_cjk(prior) and self._contains_cjk(current)):
            return None
        prior_value = re.sub(r"\s+", "", prior)
        current_value = re.sub(r"\s+", "", current)
        if current_value in prior_value:
            return prior_value
        if prior_value in current_value:
            return current_value

        max_size = min(len(prior_value), len(current_value), 48)
        for size in range(max_size, 2, -1):
            if prior_value[-size:] == current_value[:size]:
                return f"{prior_value}{current_value[size:]}"
        anchored = self._merge_cjk_anchored_prefix(prior_value, current_value)
        if anchored is not None:
            return anchored
        return None

    def _merge_cjk_anchored_prefix(self, prior_value: str, current_value: str) -> str | None:
        # CJK ASR partials often slide back to a phrase that appeared shortly before the
        # previous tail, e.g. "...辅导老师。我的学" -> "辅导老师。我的学生...".
        # Treat the repeated phrase as an anchor and replace the unstable tail. The anchor
        # may be a few characters into the new window when ASR prepends a noisy fragment.
        search_start = max(0, len(prior_value) - 96)
        tail = prior_value[search_start:]
        best_score: tuple[int, int] | None = None
        best_result: str | None = None
        max_current_start = min(12, max(0, len(current_value) - 4))
        for current_start in range(max_current_start + 1):
            max_size = min(len(current_value) - current_start, 36)
            for size in range(max_size, 3, -1):
                anchor = current_value[current_start : current_start + size]
                if not self._contains_cjk(anchor):
                    continue
                index = tail.rfind(anchor)
                if index < 0:
                    continue
                absolute_index = search_start + index
                replaced_tail = prior_value[absolute_index:]
                if len(replaced_tail) < 2 or len(replaced_tail) > 96:
                    continue
                score = (size, -current_start)
                if best_score is None or score > best_score:
                    best_score = score
                    best_result = f"{prior_value[:absolute_index]}{current_value[current_start:]}"
                break
        return best_result

    def _looks_unstable_source_word(self, word: str) -> bool:
        value = self._normalize_source_word(word)
        return len(value) <= 5 and not word.endswith((".", "!", "?"))

    def _drop_unstable_source_prefix(self, words: list[str]) -> list[str]:
        if len(words) < 3:
            return words
        value = self._normalize_source_word(words[0])
        if value in {"t", "re", "ve", "ll", "d", "s", "m"}:
            return words[1:]
        return words

    def _prefer_source_snapshot(self, prior: str, current: str) -> str:
        collapsed_current = self._collapse_source_repetition(current)
        collapsed_prior = self._collapse_source_repetition(prior)
        if collapsed_prior != prior:
            return collapsed_current
        if len(collapsed_current) + 16 < len(prior):
            return prior
        return collapsed_current

    def _collapse_source_repetition(self, text: str) -> str:
        result = text
        for _ in range(4):
            collapsed = self._collapse_source_repetition_once(result)
            if collapsed == result:
                return result
            result = collapsed
        return result

    def _collapse_source_repetition_once(self, text: str) -> str:
        cjk_collapsed = self._collapse_cjk_repetition_once(text)
        if cjk_collapsed != text:
            return cjk_collapsed

        words = text.split()
        deduped = self._collapse_adjacent_source_duplicates(words)
        if deduped != words:
            return " ".join(deduped)
        if len(words) < 6:
            return text
        normalized = self._normalize_source_words(words)
        result_words: list[str] = []
        index = 0
        while index < len(words):
            overlap = 0
            if len(result_words) >= 2:
                result_norm = self._normalize_source_words(result_words)
                max_size = min(len(result_words), len(words) - index)
                for size in range(max_size, 1, -1):
                    if result_norm[-size:] == normalized[index : index + size]:
                        overlap = size
                        break
            if overlap:
                index += overlap
                continue
            result_words.append(words[index])
            index += 1
        collapsed = " ".join(result_words)
        if collapsed != text:
            return collapsed

        for size in range(min(10, len(words) // 2), 2, -1):
            prefix = normalized[:size]
            for index in range(1, len(words) - size + 1):
                if normalized[index : index + size] == prefix:
                    return " ".join(words[index:])
        return text

    def _collapse_text_repetition(self, text: str) -> str:
        result = text
        for _ in range(4):
            collapsed = self._collapse_cjk_repetition_once(result)
            if collapsed == result:
                return result
            result = collapsed
        return result

    def _collapse_cjk_repetition_once(self, text: str) -> str:
        if not re.search(r"[\u4e00-\u9fff]", text):
            return text
        collapsed = re.sub(r"([\u4e00-\u9fff]{3,24})(?:[，,、\s]*\1)+", r"\1", text)
        return self._collapse_cjk_contained_clauses(collapsed)

    def _collapse_cjk_contained_clauses(self, text: str) -> str:
        clauses = re.findall(r"[^，,、；;。！？!?]+[，,、；;。！？!?]?", text)
        if len(clauses) < 2:
            return text

        bodies = [clause.rstrip("，,、；;。！？!?").strip() for clause in clauses]
        normalized_bodies = [re.sub(r"[\s，,、；;。！？!?]", "", body) for body in bodies]
        skip_indices: set[int] = set()
        for index, body in enumerate(normalized_bodies):
            if not body:
                continue
            nearby_start = max(0, index - 3)
            nearby_end = min(len(normalized_bodies), index + 4)
            for other_index in range(nearby_start, nearby_end):
                if other_index == index:
                    continue
                other = normalized_bodies[other_index]
                if not other or len(other) <= len(body):
                    continue
                if len(body) >= 3 and body in other:
                    skip_indices.add(index)
                    break
                if len(body) == 2 and (other.startswith(body) or other.endswith(body)):
                    skip_indices.add(index)
                    break

        kept: list[str] = []
        for index, clause in enumerate(clauses):
            if index in skip_indices:
                continue
            body = bodies[index]
            if not body:
                kept.append(clause)
                continue
            normalized_body = normalized_bodies[index]
            if kept:
                previous = kept[-1]
                previous_body = re.sub(
                    r"[\s，,、；;。！？!?]",
                    "",
                    previous.rstrip("，,、；;。！？!?").strip(),
                )
                if len(normalized_body) >= 4 and normalized_body in previous_body:
                    continue
                if len(previous_body) >= 4 and previous_body in normalized_body:
                    kept[-1] = clause
                    continue
            kept.append(clause)
        collapsed = "".join(kept)
        return collapsed if collapsed else text

    def _collapse_adjacent_source_duplicates(self, words: list[str]) -> list[str]:
        return collapse_adjacent_source_duplicates(words)

    def _normalize_source_words(self, words: list[str]) -> list[str]:
        return normalize_source_words(words)

    def _normalize_source_word(self, word: str) -> str:
        return normalize_source_word(word)

    async def _on_source(self, text: str, item_id: str | None, *, final: bool) -> None:
        if not text:
            return
        await self._maybe_align_languages(text)
        seg = self._source_segment(item_id)
        should_merge_root = self._should_merge_source_root_with_previous(
            seg, item_id, text, final=final
        )
        if self._looks_like_source_continuation(text) or should_merge_root:
            seg = self._merge_source_continuation_if_needed(seg, item_id, text)
        previous = self._raw_source_by_root.get(seg.segment_id, "")
        display_text = (
            self._collapse_source_repetition(text.strip())
            if final and item_id not in self._continuation_items
            else self._merge_source_partial(previous, text)
        )
        self._raw_source_by_root[seg.segment_id] = display_text
        if final:
            stable_final = (
                seg.status == "final"
                and previous == display_text
                and seg.end_ms > seg.start_ms
            )
            if not stable_final:
                seg.end_ms = max(self.elapsed_ms, seg.start_ms)
            self._source_final_roots.add(seg.segment_id)
        await self._emit_display_segments(seg)

    async def _on_translation(
        self, text: str, response_id: str | None, *, final: bool
    ) -> SegmentRecord | None:
        if not text:
            return None
        display_text = self._collapse_text_repetition(text.strip())
        seg = self._bind_response(response_id, display_text)
        previous = self._raw_translation_by_root.get(seg.segment_id, "")
        self._raw_translation_by_root[seg.segment_id] = display_text
        if final and seg.status != "revised":
            stable_final = (
                seg.status == "final"
                and previous == display_text
                and seg.end_ms > seg.start_ms
            )
            if not stable_final:
                seg.end_ms = max(self.elapsed_ms, seg.start_ms)
            self._translation_final_roots.add(seg.segment_id)
        await self._emit_display_segments(seg)
        await self._flush_pending_audio(response_id)
        return seg

    async def _on_audio(self, ev: Any) -> None:
        if not ev.audio or not ev.response_id:
            return
        root = self._by_response.get(ev.response_id)
        if root is None:
            self._pending_audio_by_response.setdefault(ev.response_id, []).append(ev.audio)
            return
        await self._emit_audio(root, ev.audio)

    async def _flush_pending_audio(self, response_id: str | None) -> None:
        if not response_id:
            return
        root = self._by_response.get(response_id)
        if root is None:
            return
        for audio in self._pending_audio_by_response.pop(response_id, []):
            await self._emit_audio(root, audio)

    async def _emit_audio(self, root: SegmentRecord, audio: bytes) -> None:
        segment = AudioSegment(
            segmentId=root.segment_id,
            audioBase64=base64.b64encode(audio).decode("ascii"),
            sampleRate=self._tts_sample_rate,
        )
        await self.emit({"type": "audio_segment", **segment.model_dump(by_alias=True)})

    async def _emit_display_segments(self, root: SegmentRecord) -> None:
        # LiveTranslate VAD can keep several semantic clauses in one turn, and source/target
        # punctuation counts often differ. Split both sides into readable display chunks first,
        # then align them by proportional order so the report and subtitle cards do not collapse
        # long turns into one dense paragraph.
        existing_children = self._children_by_root.get(root.segment_id, [root])
        source_final = root.segment_id in self._source_final_roots
        translation_final = root.segment_id in self._translation_final_roots
        previous_count = self._display_count_by_root.get(root.segment_id, 1)
        plan = build_display_plan(
            source_text=self._raw_source_by_root.get(root.segment_id, ""),
            translation_text=self._raw_translation_by_root.get(root.segment_id, ""),
            source_language=self.record.source_language,
            target_language=self.record.target_language,
            source_final=source_final,
            translation_final=translation_final,
            previous_count=previous_count,
            previous_source_parts=[child.source_text for child in existing_children],
            previous_translation_parts=[child.translation_text for child in existing_children],
            root_start_ms=root.start_ms,
            root_end_ms=root.end_ms,
            elapsed_ms=self.elapsed_ms,
        )
        if plan is None:
            return
        count = plan.count
        self._display_count_by_root[root.segment_id] = count
        source_display = plan.source_parts
        translation_display = plan.translation_parts
        display_final = plan.display_final
        children = self._display_children(root, count)
        bounds = plan.bounds

        for index, child in enumerate(children):
            source_text = source_display[index]
            translation_text = translation_display[index]
            start_ms, end_ms = bounds[index]
            child.item_id = root.item_id
            child.response_id = root.response_id

            is_last = index == count - 1
            source_status = "final" if source_final or not is_last else "partial"
            translation_status = "final" if translation_final or not is_last else "partial"
            next_status = translation_status if translation_text else source_status
            stable_unchanged = (
                root.segment_id in self._display_final_roots
                and child.status == "final"
                and next_status == "final"
                and child.source_text == source_text
                and child.translation_text == translation_text
                and child.end_ms > child.start_ms
            )
            if stable_unchanged:
                start_ms = child.start_ms
                end_ms = child.end_ms
            elif child.source_text or child.translation_text:
                if display_final:
                    child.start_ms = start_ms
                    child.end_ms = end_ms
                else:
                    start_ms = child.start_ms
                    end_ms = max(child.end_ms, end_ms)
                    child.start_ms = start_ms
                    child.end_ms = end_ms
            else:
                child.start_ms = start_ms
                child.end_ms = end_ms
            child.status = next_status

            if source_text or child.source_text:
                child.source_text = source_text
                await self._emit_segment(
                    "transcript_segment",
                    child,
                    language=self.record.source_language,
                    text=source_text,
                    status=source_status,
                    throttle=source_status == "partial",
                )
            if translation_text or child.translation_text:
                child.translation_text = translation_text
                if not child.original_translation:
                    child.original_translation = translation_text
                await self._emit_segment(
                    "translation_segment",
                    child,
                    language=self.record.target_language,
                    text=translation_text,
                    status=translation_status,
                    throttle=translation_status == "partial",
                )

        if display_final:
            self._display_final_roots.add(root.segment_id)

    async def _maybe_align_languages(self, text: str) -> None:
        if self._language_alignment_checked:
            return
        if self.record.source_language not in {"auto", "zh", "en"}:
            self._language_alignment_checked = True
            return
        if self.record.target_language not in {"zh", "en"}:
            self._language_alignment_checked = True
            return

        sample = self._normalize_display_text(text, "auto")
        if not sample:
            return
        inferred_source = self._infer_source_language(sample)
        if inferred_source is None:
            return

        self._lock_language_pair(inferred_source)
        self._language_alignment_checked = True

    def _infer_source_language(self, sample: str) -> str | None:
        return infer_source_language(sample)

    def _suggest_language_pair(self, inferred_source: str) -> tuple[str, str]:
        return suggest_language_pair(inferred_source, self.record.target_language)

    def _lock_language_pair(self, inferred_source: str) -> None:
        source_language, target_language = self._suggest_language_pair(inferred_source)
        self.record.source_language = source_language
        self.record.target_language = target_language
        self._reviser.update_languages(source_language, target_language)

    def _opposite_language(self, language: str) -> str:
        return opposite_language(language)

    def _display_children(self, root: SegmentRecord, count: int) -> list[SegmentRecord]:
        children = self._children_by_root.setdefault(root.segment_id, [root])
        while len(children) < count:
            self._seg_index += 1
            child = self.record.get_or_create_segment(
                f"{self.record.session_id}-seg-{self._seg_index}",
                self._seg_index,
            )
            child.start_ms = root.start_ms
            child.item_id = root.item_id
            child.response_id = root.response_id
            children.append(child)
        return children[:count]

    def _contains_cjk(self, text: str) -> bool:
        return contains_cjk(text)

    def _normalize_display_text(self, text: str, language: str | None = None) -> str:
        return normalize_display_text(text, language)

    async def _on_segment_complete(self, seg: SegmentRecord) -> None:
        if not seg.translation_text:
            return
        # 后台跨句纠偏复核（不阻塞主链路）
        recent = self.record.finalized_segments()[-self._reviser.window :]
        task = asyncio.create_task(self._run_review(list(recent)))
        self._review_tasks.add(task)
        task.add_done_callback(self._review_tasks.discard)

    async def _run_review(self, recent: list[SegmentRecord]) -> None:
        try:
            revisions = await self._reviser.review(recent)
        except Exception:  # noqa: BLE001
            return
        for rev in revisions:
            await self._apply_revision(rev)

    async def _apply_revision(self, rev: dict[str, Any]) -> None:
        seg = self.record._by_id.get(rev["segmentId"])
        if seg is None:
            return
        # Review tasks overlap by design; only apply a result that still targets
        # the current translation and has not already been revised.
        if seg.revised or seg.status == "revised" or rev["beforeText"] != seg.translation_text:
            return
        seg.translation_text = rev["afterText"]
        seg.status = "revised"
        seg.revised = True
        seg.revision_reason = rev["reason"]
        revision_id = f"{self.record.session_id}-rev-{uuid4().hex[:8]}"
        self.record.revisions.insert(
            0,
            RevisionRecord(
                revision_id=revision_id,
                target_segment_ids=[seg.segment_id],
                before_text=rev["beforeText"],
                after_text=rev["afterText"],
                reason=rev["reason"],
                confidence=rev["confidence"],
                source="llm",
                created_ms=self.elapsed_ms,
            ),
        )
        # 先发修正后的译文段（高亮 revised），再发 revision_event 供时间线展示
        await self._emit_segment(
            "translation_segment", seg, language=self.record.target_language,
            text=seg.translation_text, status="revised", throttle=False,
        )
        revision = RevisionEvent(
            revisionId=revision_id,
            targetSegmentIds=[seg.segment_id],
            beforeText=rev["beforeText"],
            afterText=rev["afterText"],
            reason=rev["reason"],
            confidence=rev["confidence"],
        )
        await self.emit({"type": "revision_event", "revision": revision.model_dump(by_alias=True)})

    async def _await_reviews(self) -> None:
        if self._stopped:
            for task in self._review_tasks:
                if not task.done():
                    task.cancel()
        if self._review_tasks:
            await asyncio.gather(*list(self._review_tasks), return_exceptions=True)

    # ---------- 事件发射 ----------
    async def _emit_segment(
        self,
        event_type: str,
        seg: SegmentRecord,
        *,
        language: str,
        text: str,
        status: str,
        throttle: bool,
    ) -> None:
        if throttle:
            key = f"{event_type}:{seg.segment_id}"
            now = time.monotonic()
            if now - self._last_partial_emit.get(key, 0.0) < PARTIAL_THROTTLE_S:
                return
            self._last_partial_emit[key] = now
        emit_key = f"{event_type}:{seg.segment_id}"
        end_ms = seg.end_ms or seg.start_ms
        signature = (text, status)
        if self._last_emitted_segment.get(emit_key) == signature:
            return
        segment = SubtitleSegment(
            segmentId=seg.segment_id,
            text=text,
            language=language,
            startMs=seg.start_ms,
            endMs=end_ms,
            status=status,  # type: ignore[arg-type]
        )
        payload = segment.model_dump(by_alias=True)
        if seg.revised and status == "revised":
            payload["originalText"] = seg.original_translation
            payload["revisionReason"] = seg.revision_reason
        await self.emit({"type": event_type, "segment": payload})
        self._last_emitted_segment[emit_key] = signature

    async def _emit_sync(
        self, status: str, lag_ms: int, message: str, source_ms: int | None = None
    ) -> None:
        state = SourceSyncState(status=status, lagMs=lag_ms, message=message, sourceMs=source_ms)  # type: ignore[arg-type]
        await self.emit({"type": "source_sync_state", "state": state.model_dump(by_alias=True)})

    async def _emit_client_clock_sync_if_due(self) -> None:
        if self._client_playback_ms is None:
            return
        now = time.monotonic()
        if now - self._last_sync_emit_at < SYNC_EMIT_INTERVAL_S:
            return
        self._last_sync_emit_at = now
        lag_ms = int(self._client_playback_ms - self.elapsed_ms)
        status = "syncing" if abs(lag_ms) <= SYNC_LAG_WARN_MS else "lagging"
        sent_delta = (
            self._client_sent_audio_ms - self.elapsed_ms
            if self._client_sent_audio_ms is not None
            else 0
        )
        await self._emit_sync(
            status,
            lag_ms,
            f"媒体同步：播放 {self._client_playback_ms // 1000:02d}s，"
            f"后端音频 {self.elapsed_ms // 1000:02d}s，发送差 {sent_delta}ms",
        )

    async def _emit_error(self, message: str) -> None:
        self.record.status = "error"
        await self.emit({"type": "error", "message": message})
