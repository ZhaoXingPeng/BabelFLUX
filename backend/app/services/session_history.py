from __future__ import annotations

import json
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from threading import Lock
from typing import Any

from app.core.config import settings
from app.services.session_store import SessionRecord


@dataclass
class HistoryEntry:
    sessionId: str
    reportId: str | None = None
    sessionName: str = ""
    productMode: str = "quick"
    inputMode: str = "demo"
    sourceLabel: str = ""
    domain: str = "通用"
    sourceLanguage: str = "auto"
    targetLanguage: str = "zh"
    status: str = "created"
    startedAt: str = ""
    endedAt: str | None = None
    durationMs: int = 0
    segmentCount: int = 0
    realtimeRevisionCount: int = 0
    finalRevisionCount: int = 0
    correctionStatus: str = "skipped"
    updatedAt: str = ""
    availableFormats: list[str] | None = None

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["availableFormats"] = self.availableFormats or []
        return data


def _fmt_ts(timestamp: float | None = None) -> str:
    return time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(timestamp or time.time()))


class SessionHistoryStore:
    def __init__(self, path: Path | None = None) -> None:
        self._path = path
        self._lock = Lock()

    @property
    def path(self) -> Path:
        if self._path is not None:
            return self._path
        path = settings.report_dir.parent / "history" / "sessions.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        return path

    def reset(self) -> None:
        with self._lock:
            try:
                self.path.unlink()
            except FileNotFoundError:
                pass

    def list(self) -> list[dict[str, Any]]:
        with self._lock:
            entries = self._read_unlocked()
        return sorted(entries, key=lambda item: item.get("updatedAt") or "", reverse=True)

    def get(self, session_id: str) -> dict[str, Any] | None:
        with self._lock:
            for entry in self._read_unlocked():
                if entry.get("sessionId") == session_id:
                    return entry
        return None

    def delete(self, session_id: str) -> bool:
        with self._lock:
            entries = self._read_unlocked()
            next_entries = [entry for entry in entries if entry.get("sessionId") != session_id]
            if len(next_entries) == len(entries):
                return False
            self._write_unlocked(next_entries)
            return True

    def upsert_from_record(
        self,
        record: SessionRecord,
        *,
        product_mode: str | None = None,
        status: str | None = None,
        report: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        with self._lock:
            entries = self._read_unlocked()
            existing = next(
                (entry for entry in entries if entry.get("sessionId") == record.session_id),
                None,
            )
            if existing is None:
                existing = {}
                entries.append(existing)

            report_data = report or record.report or {}
            metrics = report_data.get("metrics") or {}
            correction_status = report_data.get("correctionStatus") or existing.get("correctionStatus") or "skipped"
            existing.update(
                HistoryEntry(
                    sessionId=record.session_id,
                    reportId=report_data.get("reportId") or existing.get("reportId"),
                    sessionName=record.session_name,
                    productMode=product_mode or existing.get("productMode") or "quick",
                    inputMode=record.input_mode,
                    sourceLabel=record.source_label or record.source_url or record.input_mode,
                    domain=record.domain,
                    sourceLanguage=record.source_language,
                    targetLanguage=record.target_language,
                    status=status or _history_status(correction_status, record.status),
                    startedAt=existing.get("startedAt") or _fmt_ts(record.created_at),
                    endedAt=_fmt_ts(record.ended_at) if record.ended_at else existing.get("endedAt"),
                    durationMs=int(report_data.get("durationMs") or record.duration_ms or 0),
                    segmentCount=int(metrics.get("segments") or len(record.reportable_segments())),
                    realtimeRevisionCount=int(metrics.get("realtimeRevisions") or len(record.revisions)),
                    finalRevisionCount=int(metrics.get("finalRevisions") or 0),
                    correctionStatus=correction_status,
                    updatedAt=_fmt_ts(),
                    availableFormats=["txt", "srt", "md", "json"] if report_data else [],
                ).to_dict()
            )
            self._write_unlocked(entries)
            return existing

    def upsert_from_report(self, report: dict[str, Any]) -> dict[str, Any] | None:
        session_id = report.get("sessionId")
        if not session_id:
            return None

        with self._lock:
            entries = self._read_unlocked()
            existing = next(
                (entry for entry in entries if entry.get("sessionId") == session_id),
                None,
            )
            if existing is None:
                existing = {}
                entries.append(existing)

            metrics = report.get("metrics") or {}
            correction_status = report.get("correctionStatus") or existing.get("correctionStatus") or "skipped"
            existing.update(
                {
                    "sessionId": session_id,
                    "reportId": report.get("reportId") or existing.get("reportId"),
                    "sessionName": report.get("sessionName") or existing.get("sessionName") or "",
                    "productMode": existing.get("productMode") or "quick",
                    "inputMode": existing.get("inputMode") or "demo",
                    "sourceLabel": existing.get("sourceLabel") or existing.get("inputMode") or "demo",
                    "domain": report.get("domain") or existing.get("domain") or "通用",
                    "sourceLanguage": report.get("sourceLanguage") or existing.get("sourceLanguage") or "auto",
                    "targetLanguage": report.get("targetLanguage") or existing.get("targetLanguage") or "zh",
                    "status": _history_status(correction_status, existing.get("status") or ""),
                    "startedAt": existing.get("startedAt") or report.get("generatedAt") or _fmt_ts(),
                    "endedAt": existing.get("endedAt") or report.get("generatedAt"),
                    "durationMs": int(report.get("durationMs") or existing.get("durationMs") or 0),
                    "segmentCount": int(metrics.get("segments") or len(report.get("segments") or [])),
                    "realtimeRevisionCount": int(metrics.get("realtimeRevisions") or 0),
                    "finalRevisionCount": int(metrics.get("finalRevisions") or 0),
                    "correctionStatus": correction_status,
                    "updatedAt": _fmt_ts(),
                    "availableFormats": ["txt", "srt", "md", "json"],
                }
            )
            self._write_unlocked(entries)
            return existing

    def _read_unlocked(self) -> list[dict[str, Any]]:
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
        except (FileNotFoundError, json.JSONDecodeError, OSError):
            return []
        return data if isinstance(data, list) else []

    def _write_unlocked(self, entries: list[dict[str, Any]]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps(entries, ensure_ascii=False, indent=2), encoding="utf-8")


def _history_status(correction_status: str, record_status: str) -> str:
    if record_status == "running":
        return "running"
    if correction_status == "pending":
        return "correcting"
    if correction_status in {"completed", "partial"}:
        return "completed"
    if correction_status in {"fallback", "timeout", "skipped"}:
        return "fallback"
    return record_status or "created"


session_history_store = SessionHistoryStore()
