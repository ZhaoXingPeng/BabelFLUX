import json
from pathlib import Path

import pytest

from app.services.session_history import SessionHistoryStore


def _report(session_id: str, report_id: str, generated_at: str) -> dict[str, object]:
    return {
        "sessionId": session_id,
        "reportId": report_id,
        "sessionName": session_id,
        "generatedAt": generated_at,
        "correctionStatus": "completed",
        "metrics": {"segments": 1, "realtimeRevisions": 0, "finalRevisions": 0},
        "segments": [],
    }


def test_write_unlocked_preserves_json_shape_and_unicode(tmp_path: Path) -> None:
    path = tmp_path / "sessions.json"
    store = SessionHistoryStore(path)
    entries = [{"sessionId": "s1", "sessionName": "技术分享"}]

    store._write_unlocked(entries)

    assert json.loads(path.read_text(encoding="utf-8")) == entries
    assert list(tmp_path.glob(".sessions.json.tmp")) == []


def test_report_refresh_updates_timestamp_and_list_order(tmp_path: Path) -> None:
    store = SessionHistoryStore(tmp_path / "sessions.json")
    store.upsert_from_report(_report("old", "report-old", "2026-06-17 10:00:00"))
    store.upsert_from_report(_report("new", "report-new", "2026-06-17 10:01:00"))

    store.upsert_from_report(_report("old", "report-old", "2026-06-17 10:02:00"))

    entries = store.list()
    assert [entry["sessionId"] for entry in entries] == ["old", "new"]
    assert entries[0]["updatedAt"] == "2026-06-17 10:02:00"


def test_write_unlocked_keeps_previous_file_when_replace_fails(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    path = tmp_path / "sessions.json"
    store = SessionHistoryStore(path)
    original = [{"sessionId": "old", "status": "completed"}]
    store._write_unlocked(original)

    def fail_replace(self: Path, target: Path) -> Path:
        raise OSError("simulated replace failure")

    monkeypatch.setattr(Path, "replace", fail_replace)
    with pytest.raises(OSError, match="simulated replace failure"):
        store._write_unlocked([{"sessionId": "new"}])

    assert json.loads(path.read_text(encoding="utf-8")) == original
    assert list(tmp_path.glob(".sessions.json.tmp")) == []
