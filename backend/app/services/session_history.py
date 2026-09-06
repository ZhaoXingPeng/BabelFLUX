from __future__ import annotations

import json
import time
from dataclasses import asdict, dataclass
from datetime import datetime
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
    modelProfile: str = "智能默认"
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


GENERIC_FLOATING_NAMES = {"", "悬浮字幕", "悬浮自采集", "客户端悬浮"}
SOURCE_LABELS = {
    "system_audio": "系统音频",
    "system-audio": "系统音频",
    "screen_window": "屏幕窗口",
    "screen-window": "屏幕窗口",
    "browser_audio": "浏览器音频",
    "browser-tab": "浏览器音频",
    "microphone": "麦克风",
    "media_element_audio": "上传媒体",
    "video-file": "上传视频",
    "audio-file": "上传音频",
    "url": "网络视频",
    "demo": "演示视频",
}


def _is_generic_floating_name(name: str | None) -> bool:
    return (name or "").strip() in GENERIC_FLOATING_NAMES


def _source_display(input_mode: str | None, source_label: str | None) -> str:
    for value in (source_label, input_mode):
        normalized = (value or "").strip().lower()
        if normalized in SOURCE_LABELS:
            return SOURCE_LABELS[normalized]
    return "音频"


def _report_product_mode(report: dict[str, Any], existing: dict[str, Any]) -> str:
    mode = report.get("productMode") or existing.get("productMode")
    if mode:
        return str(mode)
    if _is_generic_floating_name(report.get("sessionName")):
        return "floating"
    return "quick"


def _report_input_mode(report: dict[str, Any], existing: dict[str, Any]) -> str:
    value = report.get("inputMode") or existing.get("inputMode")
    if value:
        return str(value)
    if _is_generic_floating_name(report.get("sessionName")):
        return "system_audio"
    return "demo"


def _name_timestamp(*, created_at: float | None = None, started_at: str | None = None) -> str:
    if started_at:
        for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M:%S"):
            try:
                return datetime.strptime(started_at[:19], fmt).strftime("%Y%m%d_%H%M%S")
            except ValueError:
                continue
    return time.strftime("%Y%m%d_%H%M%S", time.localtime(created_at or time.time()))


def normalize_session_name(
    name: str | None,
    *,
    product_mode: str | None,
    input_mode: str | None,
    source_label: str | None,
    created_at: float | None = None,
    started_at: str | None = None,
    existing_name: str | None = None,
) -> str:
    raw = (name or "").strip()
    existing = (existing_name or "").strip()
    if product_mode == "floating" and _is_generic_floating_name(raw):
        if existing and not _is_generic_floating_name(existing):
            return existing
        source = _source_display(input_mode, source_label)
        stamp = _name_timestamp(created_at=created_at, started_at=started_at)
        return f"悬浮同传_{source}_{stamp}"
    return raw or existing or "未命名同传"


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
            correction_status = (
                report_data.get("correctionStatus")
                or existing.get("correctionStatus")
                or "skipped"
            )
            mode = product_mode or existing.get("productMode") or "quick"
            source_label = record.source_label or record.source_url or record.input_mode
            session_name = normalize_session_name(
                report_data.get("sessionName") or record.session_name,
                product_mode=mode,
                input_mode=record.input_mode,
                source_label=source_label,
                created_at=record.created_at,
                started_at=existing.get("startedAt"),
                existing_name=existing.get("sessionName"),
            )
            existing.update(
                HistoryEntry(
                    sessionId=record.session_id,
                    reportId=report_data.get("reportId") or existing.get("reportId"),
                    sessionName=session_name,
                    productMode=mode,
                    inputMode=record.input_mode,
                    sourceLabel=source_label,
                    domain=record.domain,
                    modelProfile=record.model_profile,
                    sourceLanguage=record.source_language,
                    targetLanguage=record.target_language,
                    status=status or _history_status(correction_status, record.status),
                    startedAt=existing.get("startedAt") or _fmt_ts(record.created_at),
                    endedAt=(
                        _fmt_ts(record.ended_at)
                        if record.ended_at
                        else existing.get("endedAt")
                    ),
                    durationMs=int(report_data.get("durationMs") or record.duration_ms or 0),
                    segmentCount=int(metrics.get("segments") or len(record.reportable_segments())),
                    realtimeRevisionCount=int(
                        metrics.get("realtimeRevisions") or len(record.revisions)
                    ),
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
            correction_status = (
                report.get("correctionStatus")
                or existing.get("correctionStatus")
                or "skipped"
            )
            mode = _report_product_mode(report, existing)
            input_mode = _report_input_mode(report, existing)
            source_label = report.get("sourceLabel") or existing.get("sourceLabel") or input_mode
            session_name = normalize_session_name(
                report.get("sessionName") or existing.get("sessionName"),
                product_mode=mode,
                input_mode=input_mode,
                source_label=source_label,
                started_at=existing.get("startedAt") or report.get("generatedAt"),
                existing_name=existing.get("sessionName"),
            )
            existing.update(
                {
                    "sessionId": session_id,
                    "reportId": report.get("reportId") or existing.get("reportId"),
                    "sessionName": session_name,
                    "productMode": mode,
                    "inputMode": input_mode,
                    "sourceLabel": source_label,
                    "domain": report.get("domain") or existing.get("domain") or "通用",
                    "modelProfile": (
                        report.get("modelProfile")
                        or existing.get("modelProfile")
                        or "智能默认"
                    ),
                    "sourceLanguage": (
                        report.get("sourceLanguage")
                        or existing.get("sourceLanguage")
                        or "auto"
                    ),
                    "targetLanguage": (
                        report.get("targetLanguage")
                        or existing.get("targetLanguage")
                        or "zh"
                    ),
                    "status": _history_status(correction_status, existing.get("status") or ""),
                    "startedAt": (
                        existing.get("startedAt")
                        or report.get("generatedAt")
                        or _fmt_ts()
                    ),
                    "endedAt": existing.get("endedAt") or report.get("generatedAt"),
                    "durationMs": int(report.get("durationMs") or existing.get("durationMs") or 0),
                    "segmentCount": int(
                        metrics.get("segments") or len(report.get("segments") or [])
                    ),
                    "realtimeRevisionCount": int(metrics.get("realtimeRevisions") or 0),
                    "finalRevisionCount": int(metrics.get("finalRevisions") or 0),
                    "correctionStatus": correction_status,
                    "updatedAt": (
                        existing.get("updatedAt")
                        or report.get("generatedAt")
                        or _fmt_ts()
                    ),
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
