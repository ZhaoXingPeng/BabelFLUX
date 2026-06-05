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

PARTIAL_THROTTLE_S = 0.18
DRAIN_GRACE_S = 4.0
DRAIN_MAX_S = 30.0


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
        self._by_item: dict[str, SegmentRecord] = {}
        self._by_response: dict[str, SegmentRecord] = {}
        self._last_partial_emit: dict[str, float] = {}
        self._last_event_at = time.monotonic()
        self._review_tasks: set[asyncio.Task[Any]] = set()
        self._glossary_phrases = {
            str(t.get("sourceTerm")): str(t.get("targetTerm"))
            for t in record.glossary
            if t.get("sourceTerm") and t.get("targetTerm")
        }
        self._stopped = False

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
            frames = iter_pcm_frames(source, realtime=True, on_progress=self._on_progress)
            async with aclosing(frames) as stream:
                async for frame in stream:
                    if self._stopped:
                        break
                    await session.feed(frame)
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
            await self._emit_sync("syncing", 0, "同传进行中")
            while not self._stopped:
                frame = await queue.get()
                if frame is None:
                    break
                self._on_progress(self.elapsed_ms + int(len(frame) / 2 / 16000 * 1000))
                await session.feed(frame)
            await session.feed_silence(2.0)
            await self._drain(consumer)
        finally:
            consumer.cancel()
            await session.close()
            await self._await_reviews()
        self.record.duration_ms = self.elapsed_ms

    def stop(self) -> None:
        self._stopped = True

    # ---------- 内部 ----------
    def _on_progress(self, produced_ms: int) -> None:
        self.elapsed_ms = produced_ms

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
        # 绑定到最早一个尚未分配 response 的段（FIFO，与生成顺序一致）
        for seg in self.record.segments:
            if seg.response_id is None:
                seg.response_id = response_id
                if response_id:
                    self._by_response[response_id] = seg
                return seg
        seg = self._begin_segment(None)
        seg.response_id = response_id
        if response_id:
            self._by_response[response_id] = seg
        return seg

    async def _on_source(self, text: str, item_id: str | None, *, final: bool) -> None:
        if not text:
            return
        seg = self._source_segment(item_id)
        seg.source_text = text
        if final:
            seg.end_ms = max(self.elapsed_ms, seg.start_ms)
        await self._emit_segment(
            "transcript_segment", seg, language=self.record.source_language,
            text=text, status="final" if final else "partial", throttle=not final,
        )

    async def _on_translation(
        self, text: str, response_id: str | None, *, final: bool
    ) -> SegmentRecord | None:
        if not text:
            return None
        seg = self._bind_response(response_id)
        seg.translation_text = text
        if not seg.original_translation:
            seg.original_translation = text
        if final and seg.status != "revised":
            seg.status = "final"
            seg.end_ms = max(self.elapsed_ms, seg.start_ms)
        await self._emit_segment(
            "translation_segment", seg, language=self.record.target_language,
            text=text, status="final" if final else "partial", throttle=not final,
        )
        return seg

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
        segment = SubtitleSegment(
            segmentId=seg.segment_id,
            text=text,
            language=language,
            startMs=seg.start_ms,
            endMs=seg.end_ms or seg.start_ms,
            status=status,  # type: ignore[arg-type]
        )
        payload = segment.model_dump(by_alias=True)
        if seg.revised and status == "revised":
            payload["originalText"] = seg.original_translation
            payload["revisionReason"] = seg.revision_reason
        await self.emit({"type": event_type, "segment": payload})

    async def _emit_sync(self, status: str, lag_ms: int, message: str) -> None:
        state = SourceSyncState(status=status, lagMs=lag_ms, message=message)  # type: ignore[arg-type]
        await self.emit({"type": "source_sync_state", "state": state.model_dump(by_alias=True)})

    async def _emit_error(self, message: str) -> None:
        self.record.status = "error"
        await self.emit({"type": "error", "message": message})
