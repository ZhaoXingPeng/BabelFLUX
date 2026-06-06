import os
from pathlib import Path

from app.services import media


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

