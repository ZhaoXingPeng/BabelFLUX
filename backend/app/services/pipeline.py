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
import re
import time
from collections.abc import Awaitable, Callable
from contextlib import aclosing
from typing import Any
from uuid import uuid4

from app.core.config import Settings
from app.models.events import RevisionEvent, SourceSyncState, SubtitleSegment
from app.services.media import iter_pcm_frames
from app.services.providers.dashscope import (
    DashScopeClient,
    DashScopeConfig,
    LiveTranslateSession,
)
from app.services.revision import RealtimeReviser
from app.services.session_store import RevisionRecord, SegmentRecord, SessionRecord

Emit = Callable[[dict[str, Any]], Awaitable[None]]

PARTIAL_THROTTLE_S = 0.08
MEDIA_PROGRESS_SYNC_S = 0.5
DRAIN_GRACE_S = 4.0
DRAIN_MAX_S = 30.0
SYNC_EMIT_INTERVAL_S = 0.25
SYNC_LAG_WARN_MS = 600
SOURCE_MAX_WORDS_PER_DISPLAY_SEGMENT = 14
TARGET_MAX_CHARS_PER_DISPLAY_SEGMENT = 28
PARTIAL_DISPLAY_SEGMENT_MS = 500
FINAL_DISPLAY_SEGMENT_MS = 2000


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
        self._ws_connect = websocket_connect
        self._reviser = RealtimeReviser(
            client=self._llm_client,
            model=settings.realtime_revision_model,
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
        self._source_final_roots: set[str] = set()
        self._translation_final_roots: set[str] = set()
        self._last_partial_emit: dict[str, float] = {}
        self._last_emitted_segment: dict[str, tuple[str, str, int, int]] = {}
        self._last_event_at = time.monotonic()
        self._last_sync_emit_at = 0.0
        self._client_playback_ms: int | None = None
        self._client_sent_audio_ms: int | None = None
        self._last_media_progress_sync_at = 0.0
        self._review_tasks: set[asyncio.Task[Any]] = set()
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
        await self._emit_sync("syncing", 0, "正在连接同传引擎…")
        session = LiveTranslateSession(
            self._config,
            model=self.settings.live_translate_model,
            source_language=self.record.source_language,
            target_language=self.record.target_language,
            asr_model=self.settings.live_translate_asr_model,
            tts_enabled=self.record.tts_enabled,
            voice=self.settings.tts_voice,
            glossary=self._glossary_phrases or None,
            websocket_connect=self._ws_connect,
        )
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
            await self._drain(consumer)
        finally:
            consumer.cancel()
            await session.close()
            await self._await_reviews()
        self.record.duration_ms = self.elapsed_ms

    async def run_pcm_stream(self, queue: asyncio.Queue[bytes | None]) -> None:
        """前端采集音频经 WS 二进制流喂入；queue 收到 None 表示结束。"""
        self.record.status = "running"
        await self._emit_sync("syncing", 0, "正在连接同传引擎…")
        session = LiveTranslateSession(
            self._config,
            model=self.settings.live_translate_model,
            source_language=self.record.source_language,
            target_language=self.record.target_language,
            asr_model=self.settings.live_translate_asr_model,
            tts_enabled=self.record.tts_enabled,
            voice=self.settings.tts_voice,
            glossary=self._glossary_phrases or None,
            websocket_connect=self._ws_connect,
        )
        await session.connect()
        consumer = asyncio.create_task(self._consume(session))
        try:
            await self._emit_sync("ready", 0, "同传引擎就绪，等待音频播放")
            while not self._stopped:
                await self._wait_if_paused()
                frame = await queue.get()
                if frame is None:
                    break
                await self._wait_if_paused()
                self._on_progress(self.elapsed_ms + int(len(frame) / 2 / 16000 * 1000))
                await session.feed(frame)
                await self._emit_client_clock_sync_if_due()
            await session.feed_silence(2.0)
            await self._drain(consumer)
        finally:
            consumer.cancel()
            await session.close()
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
        deadline = time.monotonic() + DRAIN_MAX_S
        while time.monotonic() < deadline:
            if consumer.done():
                break
            if time.monotonic() - self._last_event_at > DRAIN_GRACE_S:
                break
            await asyncio.sleep(0.3)

    async def _handle(self, ev: Any) -> None:
        kind = ev.kind
        if kind == "speech_started":
            self._begin_segment(ev.item_id)
        elif kind == "source_partial":
            await self._on_source(ev.text, ev.item_id, final=False)
        elif kind == "source_final":
            await self._on_source(ev.text, ev.item_id, final=True)
        elif kind == "response_created":
            self._bind_response(ev.response_id)
        elif kind == "translation_partial":
            await self._on_translation(ev.text, ev.response_id, final=False)
        elif kind == "translation_final":
            seg = await self._on_translation(ev.text, ev.response_id, final=True)
            if seg is not None:
                await self._on_segment_complete(seg)
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

    def _bind_response(self, response_id: str | None) -> SegmentRecord:
        if response_id and response_id in self._by_response:
            return self._by_response[response_id]
        # 绑定到最早一个尚未分配 response 的模型根段（FIFO，与生成顺序一致）。
        for seg in self._roots:
            if seg.response_id is None:
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

    def _sync_child_response_ids(self, root: SegmentRecord) -> None:
        for child in self._children_by_root.get(root.segment_id, [root]):
            child.response_id = root.response_id

    def _merge_source_partial(self, previous: str, text: str) -> str:
        current = text.strip()
        if not current:
            return previous
        prior = previous.strip()
        if not prior:
            return self._collapse_source_repetition(current)

        # DashScope ASR partials can be either full snapshots or small incremental stashes.
        # Keep snapshots as-is, but append true incremental fragments so the UI never
        # regresses from a complete prefix to a trailing phrase such as "works, in fact,".
        normalized_prior = prior.rstrip(" .!?。！？")
        if current.startswith(normalized_prior) or len(current) > len(prior) * 1.2:
            return self._prefer_source_snapshot(prior, current)
        if current in prior or prior.endswith(current):
            return prior

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
        separator = "" if prior[-1].isspace() or no_space_before else " "
        return self._collapse_source_repetition(f"{prior}{separator}{current}")

    def _merge_source_overlap(self, prior: str, current: str) -> str | None:
        prior_words = prior.split()
        current_words = current.split()
        if len(prior_words) < 2 or len(current_words) < 2:
            return None
        prior_norm = self._normalize_source_words(prior_words)
        current_norm = self._normalize_source_words(current_words)
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
            for size in range(min(len(base_words), len(current_words)), 1, -1):
                if base_norm[-size:] == current_norm[:size]:
                    return " ".join([*base_words[:-size], *current_words])
        return None

    def _looks_unstable_source_word(self, word: str) -> bool:
        value = word.strip(".,;:!?，。；：！？")
        return len(value) <= 5 and not word.endswith((".", "!", "?", ",", ";", ":"))

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
        words = text.split()
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

    def _normalize_source_words(self, words: list[str]) -> list[str]:
        return [word.lower().strip(".,;:!?，。；：！？") for word in words]

    async def _on_source(self, text: str, item_id: str | None, *, final: bool) -> None:
        if not text:
            return
        seg = self._source_segment(item_id)
        previous = self._raw_source_by_root.get(seg.segment_id, "")
        display_text = (
            self._collapse_source_repetition(text.strip())
            if final
            else self._merge_source_partial(previous, text)
        )
        self._raw_source_by_root[seg.segment_id] = display_text
        if final:
            seg.end_ms = max(self.elapsed_ms, seg.start_ms)
            self._source_final_roots.add(seg.segment_id)
        await self._emit_display_segments(seg)

    async def _on_translation(
        self, text: str, response_id: str | None, *, final: bool
    ) -> SegmentRecord | None:
        if not text:
            return None
        seg = self._bind_response(response_id)
        display_text = text.strip()
        self._raw_translation_by_root[seg.segment_id] = display_text
        if final and seg.status != "revised":
            seg.end_ms = max(self.elapsed_ms, seg.start_ms)
            self._translation_final_roots.add(seg.segment_id)
        await self._emit_display_segments(seg)
        return seg

    async def _emit_display_segments(self, root: SegmentRecord) -> None:
        source_parts = self._split_source_display(
            self._raw_source_by_root.get(root.segment_id, "")
        )
        translation_parts = self._split_target_display(
            self._raw_translation_by_root.get(root.segment_id, "")
        )
        if not source_parts and not translation_parts:
            return

        current_count = max(len(source_parts), len(translation_parts), 1)
        count = max(self._display_count_by_root.get(root.segment_id, 1), current_count)
        self._display_count_by_root[root.segment_id] = count

        source_display = self._align_parts(source_parts, count, separator=" ")
        translation_display = self._align_parts(translation_parts, count, separator="")
        source_final = root.segment_id in self._source_final_roots
        translation_final = root.segment_id in self._translation_final_roots
        display_final = (not source_parts or source_final) and (
            not translation_parts or translation_final
        )
        children = self._display_children(root, count)
        bounds = self._estimate_display_bounds(
            root,
            source_display,
            translation_display,
            final=display_final,
        )

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
            time_close = (
                abs(child.start_ms - start_ms) <= 1000
                and abs(child.end_ms - end_ms) <= 1000
            )
            stable_unchanged = (
                child.status == "final"
                and next_status == "final"
                and child.source_text == source_text
                and child.translation_text == translation_text
                and child.end_ms > child.start_ms
                and time_close
            )
            if not stable_unchanged:
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

    def _split_source_display(self, text: str) -> list[str]:
        value = re.sub(r"\s+", " ", text.strip())
        if not value:
            return []

        sentence_parts = self._split_by_regex(value, r"(?<=[.!?])\s+")
        parts: list[str] = []
        for sentence in sentence_parts:
            for part in self._split_source_clauses(sentence):
                parts.extend(self._split_long_source_part(part))
        return parts

    def _split_source_clauses(self, text: str) -> list[str]:
        clauses = self._split_by_regex(text, r"(?<=[,;:])\s+")
        groups: list[str] = []
        current = ""
        for clause in clauses:
            candidate = f"{current} {clause}".strip() if current else clause
            if current and self._word_count(candidate) > SOURCE_MAX_WORDS_PER_DISPLAY_SEGMENT:
                groups.append(current)
                current = clause
            else:
                current = candidate
        if current:
            groups.append(current)
        return groups

    def _split_long_source_part(self, text: str) -> list[str]:
        words = text.split()
        if len(words) <= SOURCE_MAX_WORDS_PER_DISPLAY_SEGMENT:
            return [text]
        return [
            " ".join(words[index : index + SOURCE_MAX_WORDS_PER_DISPLAY_SEGMENT])
            for index in range(0, len(words), SOURCE_MAX_WORDS_PER_DISPLAY_SEGMENT)
        ]

    def _split_target_display(self, text: str) -> list[str]:
        value = re.sub(r"\s+", "", text.strip())
        if not value:
            return []

        raw_parts = re.findall(r"[^，,；;：:。！？]+[，,；;：:。！？]?", value)
        groups: list[str] = []
        for raw in raw_parts:
            groups.extend(self._split_long_target_part(raw))
        return [part for part in groups if part]

    def _split_long_target_part(self, text: str) -> list[str]:
        if len(text) <= TARGET_MAX_CHARS_PER_DISPLAY_SEGMENT:
            return [text]

        parts: list[str] = []
        current = ""
        clauses = re.findall(r"[^，,；;：:]+[，,；;：:]?", text)
        for clause in clauses:
            candidate = f"{current}{clause}" if current else clause
            if current and len(candidate) > TARGET_MAX_CHARS_PER_DISPLAY_SEGMENT:
                parts.append(current)
                current = clause
            else:
                current = candidate
        if current:
            parts.append(current)
        if len(parts) == 1 and len(parts[0]) > TARGET_MAX_CHARS_PER_DISPLAY_SEGMENT:
            value = parts[0]
            return [
                value[index : index + TARGET_MAX_CHARS_PER_DISPLAY_SEGMENT]
                for index in range(0, len(value), TARGET_MAX_CHARS_PER_DISPLAY_SEGMENT)
            ]
        return parts

    def _split_by_regex(self, text: str, pattern: str) -> list[str]:
        return [part.strip() for part in re.split(pattern, text) if part.strip()]

    def _word_count(self, text: str) -> int:
        return len([word for word in text.split() if word])

    def _align_parts(self, parts: list[str], count: int, *, separator: str) -> list[str]:
        if count <= 0:
            return []
        if not parts:
            return [""] * count
        if len(parts) == count:
            return parts
        if len(parts) < count:
            return [*parts, *([""] * (count - len(parts)))]

        groups: list[str] = []
        for index in range(count):
            start = (len(parts) * index) // count
            end = (len(parts) * (index + 1)) // count
            if end <= start:
                end = start + 1
            groups.append(separator.join(parts[start:end]).strip())
        return groups

    def _estimate_display_bounds(
        self,
        root: SegmentRecord,
        source_parts: list[str],
        translation_parts: list[str],
        *,
        final: bool,
    ) -> list[tuple[int, int]]:
        count = max(len(source_parts), len(translation_parts), 1)
        estimated_segment_ms = FINAL_DISPLAY_SEGMENT_MS if final else PARTIAL_DISPLAY_SEGMENT_MS
        end_ms = max(root.end_ms, self.elapsed_ms, root.start_ms + count * estimated_segment_ms)
        span = max(1, end_ms - root.start_ms)
        weights = [
            max(self._word_count(source_parts[index]), len(translation_parts[index]) // 3, 1)
            for index in range(count)
        ]
        total = sum(weights) or count
        bounds: list[tuple[int, int]] = []
        cursor = root.start_ms
        consumed = 0
        for index, weight in enumerate(weights):
            consumed += weight
            next_cursor = (
                end_ms
                if index == count - 1
                else root.start_ms + int(span * consumed / total)
            )
            bounds.append((cursor, max(next_cursor, cursor)))
            cursor = next_cursor
        return bounds

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
        signature = (text, status, seg.start_ms, end_ms)
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
