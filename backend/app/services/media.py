"""媒体解码：本地文件 / 在线 URL → 16kHz 单声道 s16le PCM 异步帧流。

通过 ffmpeg 子进程解码任意音视频（mp4/mov/webm/mp3/wav/m4a/在线直链…）为
LiveTranslate / Fun-ASR 所需的裸 PCM。默认按 ~1x 实时节奏产出帧，使云端 VAD
的断句行为与真实直播一致；消费端的节流天然对 ffmpeg 形成背压，避免长音频把
管道缓冲撑爆。
"""

from __future__ import annotations

import asyncio
import ipaddress
import os
import shutil
import socket
import time
from collections.abc import AsyncIterator, Awaitable, Callable
from pathlib import Path
from urllib.parse import urlparse

from app.core.config import PROJECT_ROOT, settings

DEFAULT_SAMPLE_RATE = 16000
BYTES_PER_SAMPLE = 2  # s16le


class MediaDecodeError(RuntimeError):
    """ffmpeg 解码失败或源不可用。"""


def _tool_executable_name(name: str) -> str:
    return f"{name}.exe" if os.name == "nt" else name


def _resolve_tool_binary(name: str) -> str | None:
    executable = _tool_executable_name(name)
    upper = name.upper()
    for env_name in (f"{upper}_PATH", f"{upper}_BINARY"):
        value = os.environ.get(env_name)
        if value and Path(value).is_file():
            return str(Path(value).resolve())

    from_path = shutil.which(name)
    if from_path:
        return from_path

    search_roots = [
        PROJECT_ROOT / "tools",
        PROJECT_ROOT.parent / "tools",
    ]
    for root in search_roots:
        if not root.exists():
            continue
        matches = sorted(root.glob(f"**/{executable}"), key=lambda path: len(str(path)))
        for match in matches:
            if match.is_file():
                return str(match.resolve())
    return None


def ffmpeg_available() -> bool:
    return _resolve_tool_binary("ffmpeg") is not None


def _is_url(source: str) -> bool:
    return urlparse(source).scheme in {"http", "https"}


def _host_matches_allowed_list(host: str, allowed_hosts: list[str]) -> bool:
    normalized = host.rstrip(".").lower()
    for allowed in allowed_hosts:
        candidate = allowed.strip().rstrip(".").lower()
        if not candidate:
            continue
        if candidate.startswith("*."):
            suffix = candidate[1:]
            if normalized.endswith(suffix) and normalized != candidate[2:]:
                return True
            continue
        if normalized == candidate:
            return True
    return False


def _configured_allowed_hosts() -> list[str]:
    raw = getattr(settings, "allowed_media_hosts", "") or ""
    return [item.strip() for item in raw.split(",") if item.strip()]


def _is_forbidden_ip(address: ipaddress.IPv4Address | ipaddress.IPv6Address) -> bool:
    return (
        address.is_private
        or address.is_loopback
        or address.is_link_local
        or address.is_multicast
        or address.is_reserved
        or address.is_unspecified
    )


def _validate_remote_media_url(source: str) -> None:
    parsed = urlparse(source)
    if parsed.scheme not in {"http", "https"}:
        raise MediaDecodeError("在线媒体 URL 仅支持 http/https")
    if not parsed.hostname:
        raise MediaDecodeError("在线媒体 URL 缺少 host")

    host = parsed.hostname.rstrip(".").lower()
    allowed_hosts = _configured_allowed_hosts()
    if allowed_hosts and not _host_matches_allowed_list(host, allowed_hosts):
        raise MediaDecodeError("在线媒体 URL host 不在白名单内")

    try:
        direct_ip = ipaddress.ip_address(host)
    except ValueError:
        direct_ip = None
    if direct_ip is not None:
        if _is_forbidden_ip(direct_ip):
            raise MediaDecodeError("在线媒体 URL 不允许访问内网或本机地址")
        return

    if host == "localhost" or host.endswith(".localhost"):
        raise MediaDecodeError("在线媒体 URL 不允许访问本机地址")

    try:
        resolved = socket.getaddrinfo(host, None, type=socket.SOCK_STREAM)
    except socket.gaierror as exc:
        raise MediaDecodeError("在线媒体 URL host 无法解析") from exc

    for family, _, _, _, sockaddr in resolved:
        if family not in (socket.AF_INET, socket.AF_INET6):
            continue
        if _is_forbidden_ip(ipaddress.ip_address(sockaddr[0])):
            raise MediaDecodeError("在线媒体 URL 解析到内网或本机地址")


def frame_size_bytes(sample_rate: int = DEFAULT_SAMPLE_RATE, frame_ms: int = 40) -> int:
    return int(sample_rate * frame_ms / 1000) * BYTES_PER_SAMPLE


def _build_ffmpeg_args(source: str, sample_rate: int) -> list[str]:
    ffmpeg = _resolve_tool_binary("ffmpeg") or "ffmpeg"
    args = [ffmpeg, "-nostdin", "-hide_banner", "-loglevel", "error"]
    if _is_url(source):
        _validate_remote_media_url(source)
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
    ffprobe = _resolve_tool_binary("ffprobe")
    if ffprobe is None:
        return None
    args = [
        ffprobe, "-v", "error",
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
    frame_ms: int = 40,
    realtime: bool = True,
    speed: float = 1.0,
    on_progress: Callable[[int], None] | None = None,
    pause_wait: Callable[[], Awaitable[float]] | None = None,
) -> AsyncIterator[bytes]:
    """逐帧产出 PCM。

    参数:
        source: 本地路径或 http(s) 直链。
        frame_ms: 每帧时长（40ms = 1280 字节 @16k）。
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
