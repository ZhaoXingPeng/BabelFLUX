"""媒体解码：本地文件 / 在线 URL → 16kHz 单声道 s16le PCM 异步帧流。

通过 ffmpeg 子进程解码任意音视频（mp4/mov/webm/mp3/wav/m4a/在线直链…）为
LiveTranslate / Fun-ASR 所需的裸 PCM。默认按 ~1x 实时节奏产出帧，使云端 VAD
的断句行为与真实直播一致；消费端的节流天然对 ffmpeg 形成背压，避免长音频把
管道缓冲撑爆。
"""

from __future__ import annotations

import asyncio
import shutil
import time
from collections.abc import AsyncIterator, Awaitable, Callable
from pathlib import Path

DEFAULT_SAMPLE_RATE = 16000
BYTES_PER_SAMPLE = 2  # s16le


class MediaDecodeError(RuntimeError):
    """ffmpeg 解码失败或源不可用。"""


def ffmpeg_available() -> bool:
    return shutil.which("ffmpeg") is not None


def _is_url(source: str) -> bool:
    return source.startswith(("http://", "https://", "rtmp://", "rtsp://"))


def frame_size_bytes(sample_rate: int = DEFAULT_SAMPLE_RATE, frame_ms: int = 100) -> int:
    return int(sample_rate * frame_ms / 1000) * BYTES_PER_SAMPLE


def _build_ffmpeg_args(source: str, sample_rate: int) -> list[str]:
    args = ["ffmpeg", "-nostdin", "-hide_banner", "-loglevel", "error"]
    if _is_url(source):
        # 在线直链/直播：断流自动重连，提升健壮性。
        args += [
            "-reconnect", "1",
            "-reconnect_streamed", "1",
            "-reconnect_delay_max", "5",
        ]
    args += [
        "-i", source,
        "-vn",  # 丢弃视频，仅取音频
        "-ac", "1",
        "-ar", str(sample_rate),
        "-f", "s16le",
        "pipe:1",
    ]
    return args


async def probe_duration_seconds(source: str) -> float | None:
    """用 ffprobe 探测时长（秒）；失败返回 None。"""
    if shutil.which("ffprobe") is None:
        return None
    args = [
        "ffprobe", "-v", "error",
        "-show_entries", "format=duration",
        "-of", "default=noprint_wrappers=1:nokey=1",
        source,
    ]
    try:
        proc = await asyncio.create_subprocess_exec(
            *args,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.DEVNULL,
        )
        stdout, _ = await asyncio.wait_for(proc.communicate(), timeout=20)
        value = stdout.decode().strip()
        return float(value) if value and value != "N/A" else None
    except (TimeoutError, ValueError, OSError):
        return None


async def iter_pcm_frames(
    source: str,
    *,
    sample_rate: int = DEFAULT_SAMPLE_RATE,
    frame_ms: int = 100,
    realtime: bool = True,
    speed: float = 1.0,
    on_progress: Callable[[int], None] | None = None,
    pause_wait: Callable[[], Awaitable[float]] | None = None,
) -> AsyncIterator[bytes]:
    """逐帧产出 PCM。

    参数:
        source: 本地路径或 http(s) 直链。
        frame_ms: 每帧时长（100ms = 3200 字节 @16k）。
        realtime: True 时按 frame_ms/speed 的节奏产出，模拟直播；False 尽快产出。
        speed: 实时倍速（1.0=原速，>1 更快，便于压测）。
        on_progress: 回调累计已产出毫秒数。
    """
    if not ffmpeg_available():
        raise MediaDecodeError("系统未安装 ffmpeg，无法解码媒体源")

    if not _is_url(source) and not Path(source).exists():
        raise MediaDecodeError(f"媒体文件不存在: {source}")

    args = _build_ffmpeg_args(source, sample_rate)
    chunk = frame_size_bytes(sample_rate, frame_ms)
    interval = (frame_ms / 1000.0) / max(speed, 0.01)

    proc = await asyncio.create_subprocess_exec(
        *args,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    assert proc.stdout is not None

    start = time.monotonic()
    index = 0
    produced_ms = 0
    try:
        while True:
            if pause_wait is not None:
                start += await pause_wait()
            try:
                data = await proc.stdout.readexactly(chunk)
            except asyncio.IncompleteReadError as exc:
                data = exc.partial
                if data:
                    produced_ms += int(len(data) / BYTES_PER_SAMPLE / sample_rate * 1000)
                    if on_progress:
                        on_progress(produced_ms)
                    yield data
                break

            produced_ms += frame_ms
            if on_progress:
                on_progress(produced_ms)
            yield data
            index += 1

            if realtime:
                # 防漂移：对齐到 start + index*interval 的绝对时刻。
                target = start + index * interval
                delay = target - time.monotonic()
                if delay > 0:
                    await asyncio.sleep(delay)

        return_code = await proc.wait()
        if return_code not in (0, None):
            stderr = (await proc.stderr.read()).decode(errors="replace") if proc.stderr else ""
            raise MediaDecodeError(f"ffmpeg 退出码 {return_code}: {stderr[:400]}")
    finally:
        if proc.returncode is None:
            try:
                proc.terminate()
            except ProcessLookupError:
                pass
            try:
                await asyncio.wait_for(proc.wait(), timeout=3)
            except (TimeoutError, ProcessLookupError):
                try:
                    proc.kill()
                except ProcessLookupError:
                    pass
