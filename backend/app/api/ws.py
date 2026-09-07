"""会话 WebSocket：把同传管线接到前端。

客户端在连接后发送 start_session 启动同传；服务端按会话的 inputMode 选择音频入口：
    - url                         → 后端用 ffmpeg 从在线直链解码并喂入；
    - 采集类（microphone/browser_audio/screen_window/media_element_audio/system_audio）
                                  → 前端把 PCM 以 WS 二进制帧推来；
    - demo                        → 演示事件流（或 DEMO_MEDIA_PATH 指向的样例媒体）。
会话自然结束或客户端发送 stop_session 时，触发会后完整纠偏并生成报告，
随后下发 session_report{reportId}，前端据此拉取/下载报告。
"""

import asyncio
import json
import time
from pathlib import Path
from typing import Any

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from app.api.handoff_ws import serve_handoff_socket
from app.core.config import settings
from app.services.handoff import handoff_tokens
from app.services.mock_session import run_mock_session
from app.services.pipeline import InterpretationPipeline
from app.services.providers.dashscope import DashScopeClient, DashScopeConfig
from app.services.report import generate_session_report
from app.services.session_commands import (
    parse_client_payload,
    parse_clock_ms,
    parse_session_overrides,
)
from app.services.session_events import session_event_hub
from app.services.session_history import session_history_store
from app.services.session_store import session_store

router = APIRouter(tags=["websocket"])
_REPORT_TASKS: set[asyncio.Task[None]] = set()

CLIENT_CAPTURE_MODES = {
    "microphone",
    "browser_audio",
    "screen_window",
    "media_element_audio",
    "system_audio",
}
PCM_FRAME_MS = 40
MAX_PCM_QUEUE_AUDIO_MS = 1_000
MAX_PCM_QUEUE_FRAMES = MAX_PCM_QUEUE_AUDIO_MS // PCM_FRAME_MS


@router.websocket("/ws/sessions/{session_id}")
async def session_socket(websocket: WebSocket, session_id: str) -> None:
    await websocket.accept()
    ws_token = websocket.query_params.get("token")
    if not ws_token:
        await websocket.send_json({"type": "error", "message": "Missing WebSocket token"})
        await websocket.close(code=4401)
        return

    if handoff_tokens.validate_ws_token(session_id, ws_token, purpose="handoff"):
        await serve_handoff_socket(websocket, session_id)
        return

    if not handoff_tokens.validate_ws_token(session_id, ws_token, purpose="session"):
        await websocket.send_json({"type": "error", "message": "Invalid WebSocket token"})
        await websocket.close(code=4401)
        return

    record = session_store.get_or_create(session_id)
    await websocket.send_json({"type": "session_started", "sessionId": session_id})

    lock = asyncio.Lock()

    async def emit(event: dict[str, Any]) -> None:
        async with lock:
            try:
                await websocket.send_json(event)
            except (RuntimeError, WebSocketDisconnect):
                # 客户端已断开/连接已关闭：报告等结果已落盘，可经 REST 拉取，忽略发送异常。
                pass
        session_event_hub.publish(session_id, event)

    state: dict[str, Any] = {
        "pipeline": None,
        "run_task": None,
        "pcm_queue": None,
        "finalized": False,
    }

    async def finalize() -> None:
        if state["finalized"]:
            return
        state["finalized"] = True
        record.status = "ended"
        record.ended_at = time.time()
        client = _build_llm_client()
        try:
            report = await generate_session_report(
                record,
                settings=settings,
                client=None,
                run_final_correction=False,
                pending_final_correction=client is not None and bool(record.reportable_segments()),
            )
            _persist_report(report)
            history = session_history_store.upsert_from_record(record, report=report)
            await emit(
                {
                    "type": "session_report",
                    "reportId": report["reportId"],
                    "correctionStatus": report.get("correctionStatus"),
                    "historyStatus": history.get("status"),
                }
            )
            if client is not None and record.reportable_segments():
                _schedule_final_report_correction(record, report["reportId"], emit)
        except Exception as exc:  # noqa: BLE001 - 报告失败也要让前端收到提示
            await emit({"type": "error", "message": f"报告生成失败：{exc}"})

    async def run_and_finalize() -> None:
        try:
            await _run_ingest(record, state, emit)
        except Exception as exc:  # noqa: BLE001
            await emit({"type": "error", "message": f"同传运行异常：{exc}"})
        await finalize()

    try:
        while True:
            message = await websocket.receive()
            if message.get("type") == "websocket.disconnect":
                break

            data_bytes = message.get("bytes")
            if data_bytes is not None:
                queue = state["pcm_queue"]
                if queue is not None:
                    _put_pcm_frame(queue, data_bytes)
                    # Browser media capture can deliver audio frames steadily enough that
                    # the receive loop keeps draining socket messages before the ingest
                    # task gets scheduled. Yield briefly so the PCM consumer can feed the
                    # realtime model instead of letting the bounded queue stay full.
                    await asyncio.sleep(0.001)
                continue

            text = message.get("text")
            if not text:
                continue
            try:
                payload, error_message = parse_client_payload(text)
            except json.JSONDecodeError:
                await emit({"type": "error", "message": "Invalid JSON message"})
                continue
            if error_message:
                await emit({"type": "error", "message": error_message})
                continue

            assert payload is not None
            mtype = payload.get("type")
            if mtype == "start_session":
                if state["run_task"] is None:
                    override_error = _apply_overrides(record, payload)
                    if override_error:
                        await emit({"type": "error", "message": override_error})
                        continue
                    state["run_task"] = asyncio.create_task(run_and_finalize())
            elif mtype == "media_clock":
                playback_ms = parse_clock_ms(payload.get("playbackMs"))
                sent_audio_ms = parse_clock_ms(payload.get("sentAudioMs"))
                if playback_ms is None or sent_audio_ms is None:
                    await emit(
                        {
                            "type": "error",
                            "message": "media_clock 的 playbackMs 和 sentAudioMs 必须是非负整数",
                        }
                    )
                    continue
                pipeline = state["pipeline"]
                if pipeline is not None:
                    pipeline.update_client_clock(playback_ms, sent_audio_ms)
            elif mtype == "audio_chunk_end" or mtype == "audio_end":
                if state["pcm_queue"] is not None:
                    _put_pcm_end(state["pcm_queue"])
            elif mtype == "stop_session":
                if state["pipeline"] is not None:
                    state["pipeline"].stop()
                if state["pcm_queue"] is not None:
                    _put_pcm_end(state["pcm_queue"])
                if state["run_task"] is not None:
                    await state["run_task"]
                else:
                    await finalize()
                break
            elif mtype == "pause_session":
                if state["pipeline"] is not None:
                    state["pipeline"].pause()
                await emit(
                    {
                        "type": "source_sync_state",
                        "state": {"status": "missing", "lagMs": 0, "message": "会话已暂停"},
                    }
                )
            elif mtype == "resume_session":
                if state["pipeline"] is not None:
                    state["pipeline"].resume()
                await emit(
                    {
                        "type": "source_sync_state",
                        "state": {"status": "syncing", "lagMs": 160, "message": "会话已继续"},
                    }
                )
            else:
                await emit({"type": "error", "message": "Unsupported client event"})
    except WebSocketDisconnect:
        pass
    finally:
        if state["pipeline"] is not None:
            state["pipeline"].stop()
        if state["pcm_queue"] is not None:
            _put_pcm_end(state["pcm_queue"])
        run_task = state["run_task"]
        if run_task is not None and not run_task.done():
            try:
                await asyncio.wait_for(run_task, timeout=10)
            except (TimeoutError, asyncio.CancelledError, Exception):  # noqa: BLE001
                run_task.cancel()


async def _run_ingest(record: Any, state: dict[str, Any], emit: Any) -> None:
    input_mode = record.input_mode
    if not settings.use_real_pipeline:
        await run_mock_session(record, emit)
        return

    if input_mode == "demo":
        demo_path = _demo_media_path()
        if demo_path is None:
            await run_mock_session(record, emit)
            return
        pipeline = InterpretationPipeline(settings=settings, record=record, emit=emit)
        state["pipeline"] = pipeline
        await pipeline.run_media(demo_path)
        return

    pipeline = InterpretationPipeline(settings=settings, record=record, emit=emit)
    state["pipeline"] = pipeline

    if input_mode in CLIENT_CAPTURE_MODES:
        queue: asyncio.Queue[bytes | None] = asyncio.Queue(maxsize=MAX_PCM_QUEUE_FRAMES)
        state["pcm_queue"] = queue
        await pipeline.run_pcm_stream(queue)
        return

    if input_mode == "url":
        url = record.source_url
        if not url:
            await emit({"type": "error", "message": "缺少在线媒体 URL"})
            return
        await pipeline.run_media(url)
        return

    await emit({"type": "error", "message": f"暂不支持的输入模式：{input_mode}"})


def _put_pcm_frame(queue: asyncio.Queue[bytes | None], frame: bytes) -> None:
    # 队列只在已积压约 1 秒音频时丢最旧帧，优先保证实时性而不是播放过期音频。
    while queue.full():
        try:
            queue.get_nowait()
        except asyncio.QueueEmpty:
            break
    queue.put_nowait(frame)


def _put_pcm_end(queue: asyncio.Queue[bytes | None]) -> None:
    while queue.full():
        try:
            queue.get_nowait()
        except asyncio.QueueEmpty:
            break
    queue.put_nowait(None)


def _parse_client_payload(text: str) -> tuple[dict[str, Any] | None, str | None]:
    return parse_client_payload(text)


def _parse_clock_ms(value: Any) -> int | None:
    return parse_clock_ms(value)


def _apply_overrides(record: Any, payload: dict[str, Any]) -> str | None:
    """Validate and apply the small set of start_session overrides."""
    overrides, error_message = parse_session_overrides(payload)
    if error_message:
        return error_message
    assert overrides is not None
    for attribute, value in overrides.as_record_updates().items():
        setattr(record, attribute, value)
    return None


def _build_llm_client() -> DashScopeClient | None:
    if not settings.use_real_pipeline:
        return None
    try:
        return DashScopeClient(DashScopeConfig.from_settings(settings))
    except Exception:  # noqa: BLE001
        return None


def _schedule_final_report_correction(
    record: Any,
    report_id: str,
    emit: Any,
) -> None:
    async def runner() -> None:
        client = _build_llm_client()
        if client is None:
            report = await generate_session_report(
                record,
                settings=settings,
                client=None,
                report_id=report_id,
            )
            _persist_report(report)
            history = session_history_store.upsert_from_record(record, report=report)
            await emit(
                {
                    "type": "session_report",
                    "reportId": report["reportId"],
                    "correctionStatus": report.get("correctionStatus"),
                    "historyStatus": history.get("status"),
                }
            )
            return
        try:
            report = await generate_session_report(
                record,
                settings=settings,
                client=client,
                report_id=report_id,
            )
            _persist_report(report)
            history = session_history_store.upsert_from_record(record, report=report)
            await emit(
                {
                    "type": "session_report",
                    "reportId": report["reportId"],
                    "correctionStatus": report.get("correctionStatus"),
                    "historyStatus": history.get("status"),
                }
            )
        except Exception:
            report = await generate_session_report(
                record,
                settings=settings,
                client=None,
                report_id=report_id,
            )
            _persist_report(report)
            history = session_history_store.upsert_from_record(record, report=report)
            await emit(
                {
                    "type": "session_report",
                    "reportId": report["reportId"],
                    "correctionStatus": report.get("correctionStatus"),
                    "historyStatus": history.get("status"),
                }
            )

    task = asyncio.create_task(runner())
    _REPORT_TASKS.add(task)
    task.add_done_callback(_REPORT_TASKS.discard)


def _persist_report(report: dict[str, Any]) -> None:
    path = settings.report_dir / f"{report['reportId']}.json"
    try:
        path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    except OSError:
        pass


def _demo_media_path() -> str | None:
    raw = getattr(settings, "demo_media_path", "") or ""
    if raw and Path(raw).exists():
        return raw
    return None
