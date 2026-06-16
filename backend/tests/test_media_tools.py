import os
import socket
from pathlib import Path

import pytest

from app.core.config import settings
from app.services import media

AddrInfo = tuple[int, int, int, str, tuple[str, int]]


def test_default_pcm_frame_size_is_low_latency() -> None:
    assert media.frame_size_bytes() == 1280


def test_resolve_ffmpeg_from_parent_tools_when_path_is_missing(monkeypatch, tmp_path: Path) -> None:
    project_root = tmp_path / "repo"
    ffmpeg_dir = tmp_path / "tools" / "ffmpeg-test" / "bin"
    project_root.mkdir()
    ffmpeg_dir.mkdir(parents=True)
    executable = ffmpeg_dir / ("ffmpeg.exe" if os.name == "nt" else "ffmpeg")
    executable.write_bytes(b"stub")

    monkeypatch.setattr(media, "PROJECT_ROOT", project_root)
    monkeypatch.setenv("PATH", "")
    monkeypatch.delenv("FFMPEG_PATH", raising=False)
    monkeypatch.delenv("FFMPEG_BINARY", raising=False)

    assert media._resolve_tool_binary("ffmpeg") == str(executable.resolve())
    assert media.ffmpeg_available()


@pytest.mark.parametrize(
    "url",
    [
        "ftp://example.com/audio.wav",
        "rtmp://example.com/live",
        "http://127.0.0.1/audio.wav",
        "http://10.0.0.12/audio.wav",
        "http://172.16.0.5/audio.wav",
        "http://192.168.1.4/audio.wav",
        "http://169.254.169.254/latest/meta-data/",
        "http://localhost/audio.wav",
    ],
)
def test_remote_media_url_rejects_unsafe_sources(url: str) -> None:
    with pytest.raises(media.MediaDecodeError):
        media._validate_remote_media_url(url)


def test_remote_media_url_rejects_hosts_resolving_to_private_ip(monkeypatch) -> None:
    def fake_getaddrinfo(*_: object, **__: object) -> list[AddrInfo]:
        return [(socket.AF_INET, socket.SOCK_STREAM, 0, "", ("10.1.2.3", 0))]

    monkeypatch.setattr(media.socket, "getaddrinfo", fake_getaddrinfo)

    with pytest.raises(media.MediaDecodeError):
        media._validate_remote_media_url("https://media.example.com/audio.wav")


def test_remote_media_url_allows_public_http_host(monkeypatch) -> None:
    def fake_getaddrinfo(*_: object, **__: object) -> list[AddrInfo]:
        return [(socket.AF_INET, socket.SOCK_STREAM, 0, "", ("93.184.216.34", 0))]

    monkeypatch.setattr(media.socket, "getaddrinfo", fake_getaddrinfo)

    media._validate_remote_media_url("https://media.example.com/audio.wav")


def test_remote_media_url_respects_allowed_media_hosts(monkeypatch) -> None:
    original = settings.allowed_media_hosts
    object.__setattr__(settings, "allowed_media_hosts", "media.example.com")
    try:
        with pytest.raises(media.MediaDecodeError):
            media._validate_remote_media_url("https://other.example.com/audio.wav")
    finally:
        object.__setattr__(settings, "allowed_media_hosts", original)


def test_ffmpeg_args_reject_unsafe_url_before_launch() -> None:
    with pytest.raises(media.MediaDecodeError):
        media._build_ffmpeg_args("http://127.0.0.1/audio.wav", media.DEFAULT_SAMPLE_RATE)
