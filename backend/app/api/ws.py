"""会话 WebSocket：把同传管线接到前端。

客户端在连接后发送 start_session 启动同传；服务端按会话的 inputMode 选择音频入口：
    - url                         → 后端用 ffmpeg 从在线直链解码并喂入；
    - upload_video / upload_audio → 解码先前上传到 /sessions/{id}/media 的文件；
    - 采集类（microphone/browser_audio/screen_window/system_audio）
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

from app.core.config import settings
from app.services.handoff import handoff_tokens
from app.services.pipeline import InterpretationPipeline
from app.services.providers.dashscope import DashScopeClient, DashScopeConfig
from app.services.providers.mock import build_mock_events
from app.services.report import generate_session_report
from app.services.session_store import session_store

router = APIRouter(tags=["websocket"])

CLIENT_CAPTURE_MODES = {"microphone", "browser_audio", "screen_window", "system_audio"}


@router.websocket("/ws/sessions/{session_id}")
async def session_socket(websocket: WebSocket, session_id: str) -> None:
    await websocket.accept()
    ws_token = websocket.query_params.get("token")
    if ws_token and not handoff_tokens.validate_ws_token(session_id, ws_token):
        await websocket.send_json({"type": "error", "message": "Invalid handoff WebSocket token"})
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
            report = await generate_session_report(record, settings=settings, client=client)
            _persist_report(report)
            await emit({"type": "session_report", "reportId": report["reportId"]})
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
                    queue.put_nowait(data_bytes)
                continue

            text = message.get("text")
            if not text:
                continue
            try:
                payload = json.loads(text)
            except json.JSONDecodeError:
                await emit({"type": "error", "message": "Invalid JSON message"})
                continue

            mtype = payload.get("type")
            if mtype == "start_session":
                if state["run_task"] is None:
                    _apply_overrides(record, payload)
                    state["run_task"] = asyncio.create_task(run_and_finalize())
            elif mtype == "audio_chunk_end" or mtype == "audio_end":
                if state["pcm_queue"] is not None:
                    state["pcm_queue"].put_nowait(None)
            elif mtype == "stop_session":
                if state["pipeline"] is not None:
                    state["pipeline"].stop()
                if state["pcm_queue"] is not None:
                    state["pcm_queue"].put_nowait(None)
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
            state["pcm_queue"].put_nowait(None)
        run_task = state["run_task"]
        if run_task is not None and not run_task.done():
            try:
                await asyncio.wait_for(run_task, timeout=10)
            except (TimeoutError, asyncio.CancelledError, Exception):  # noqa: BLE001
                run_task.cancel()


async def _run_ingest(record: Any, state: dict[str, Any], emit: Any) -> None:
    input_mode = record.input_mode
    if not settings.use_real_pipeline:
        await _run_mock(record.session_id, emit)
        return

    if input_mode == "demo":
        demo_path = _demo_media_path()
        if demo_path is None:
            await _run_mock(record.session_id, emit)
            return
        pipeline = InterpretationPipeline(settings=settings, record=record, emit=emit)
        state["pipeline"] = pipeline
        await pipeline.run_media(demo_path)
        return

    pipeline = InterpretationPipeline(settings=settings, record=record, emit=emit)
    state["pipeline"] = pipeline

    if input_mode in CLIENT_CAPTURE_MODES:
        queue: asyncio.Queue[bytes | None] = asyncio.Queue()
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

    if input_mode in ("upload_video", "upload_audio"):
        media_path = record.media_path
        if not media_path or not Path(media_path).exists():
            await emit({"type": "error", "message": "未找到已上传的媒体文件，请先上传"})
            return
        await pipeline.run_media(media_path)
        return

    await emit({"type": "error", "message": f"暂不支持的输入模式：{input_mode}"})


async def _run_mock(session_id: str, emit: Any) -> None:
    for event in build_mock_events(session_id):
        await emit(event)
        await asyncio.sleep(0.25)


def _apply_overrides(record: Any, payload: dict[str, Any]) -> None:
    """允许 start_session 携带少量覆盖项（语种/领域/源），增强健壮性。"""
    if payload.get("sourceLanguage"):
        lang = payload["sourceLanguage"]
        record.source_language = "en" if lang == "auto" else lang
    if payload.get("targetLanguage"):
        record.target_language = payload["targetLanguage"]
    if payload.get("domain"):
        record.domain = payload["domain"]
    if payload.get("inputMode"):
        record.input_mode = payload["inputMode"]
    if payload.get("sourceUrl"):
        record.source_url = payload["sourceUrl"]


def _build_llm_client() -> DashScopeClient | None:
    if not settings.use_real_pipeline:
        return None
    try:
        return DashScopeClient(DashScopeConfig.from_settings(settings))
    except Exception:  # noqa: BLE001
        return None


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
