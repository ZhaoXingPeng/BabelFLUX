from datetime import datetime
from typing import Any, Literal
from urllib.parse import quote, urlencode
from uuid import uuid4

from fastapi import APIRouter, HTTPException
from fastapi.responses import JSONResponse, PlainTextResponse
from pydantic import BaseModel, Field

from app.core.config import settings
from app.services.handoff import DisplayMode, HandoffTokenError, handoff_tokens
from app.services.report import render_md, render_srt, render_txt
from app.services.session_history import session_history_store
from app.services.session_store import session_store

router = APIRouter(prefix="/sessions", tags=["sessions"])


class GlossaryTermPayload(BaseModel):
    source_term: str = Field(alias="sourceTerm")
    target_term: str = Field(alias="targetTerm")
    priority: int = 0
    note: str | None = None


class CreateSessionRequest(BaseModel):
    input_mode: Literal[
        "demo",
        "url",
        "microphone",
        "browser_audio",
        "screen_window",
        "media_element_audio",
        "system_audio",
    ] = Field(default="demo", alias="inputMode")
    source_language: str = Field(default="en", alias="sourceLanguage")
    target_language: str = Field(default="zh", alias="targetLanguage")
    product_mode: Literal["quick", "floating"] = Field(default="quick", alias="productMode")
    session_name: str = Field(default="未命名同传", alias="sessionName")
    domain: str = "通用"
    model_profile: str = Field(default="智能默认", alias="modelProfile")
    source_key: str = Field(default="demo", alias="sourceKey")
    source_file_name: str | None = Field(default=None, alias="sourceFileName")
    source_url: str | None = Field(default=None, alias="sourceUrl")
    source_permission: Literal["idle", "requesting", "granted", "denied"] = Field(
        default="idle",
        alias="sourcePermission",
    )
    tts_enabled: bool = Field(default=False, alias="ttsEnabled")
    glossary: list[GlossaryTermPayload] = Field(default_factory=list)


class CreateSessionResponse(BaseModel):
    session_id: str = Field(alias="sessionId")
    ws_token: str = Field(alias="wsToken")
    status: str


class IssueHandoffRequest(BaseModel):
    source: str | None = None
    source_language: str | None = Field(default=None, alias="sourceLanguage")
    target_language: str | None = Field(default=None, alias="targetLanguage")
    display_mode: DisplayMode = Field(default="bilingual", alias="displayMode")


class IssueHandoffResponse(BaseModel):
    handoff_token: str = Field(alias="handoffToken")
    expires_at: datetime = Field(alias="expiresAt")
    deep_link_url: str = Field(alias="deepLinkUrl")


class ClaimHandoffRequest(BaseModel):
    token: str


class ClaimHandoffResponse(BaseModel):
    session_id: str = Field(alias="sessionId")
    ws_url: str = Field(alias="wsUrl")
    ws_token: str = Field(alias="wsToken")
    source: str | None
    source_language: str | None = Field(alias="sourceLanguage")
    target_language: str | None = Field(alias="targetLanguage")
    display_mode: DisplayMode = Field(alias="displayMode")
    expires_at: datetime = Field(alias="expiresAt")


class SessionHistoryListResponse(BaseModel):
    items: list[dict[str, Any]]


def _normalize_source_language(code: str | None) -> str:
    return code or "auto"


def _register_session(req: CreateSessionRequest) -> str:
    session_id = str(uuid4())
    session_store.create(
        session_id,
        source_language=_normalize_source_language(req.source_language),
        target_language=req.target_language or "zh",
        domain=req.domain,
        session_name=req.session_name,
        glossary=[t.model_dump(by_alias=True) for t in req.glossary],
        tts_enabled=req.tts_enabled,
        input_mode=req.input_mode,
        source_label=req.source_file_name or req.source_url or req.source_key,
    )
    record = session_store.get(session_id)
    if record is not None and req.source_url:
        record.source_url = req.source_url
    if record is not None:
        session_history_store.upsert_from_record(
            record,
            product_mode=req.product_mode,
            status="created",
        )
    return session_id


@router.post("", response_model=CreateSessionResponse, response_model_by_alias=True)
def create_session(req: CreateSessionRequest) -> CreateSessionResponse:
    session_id = _register_session(req)
    ws_token = handoff_tokens.issue_ws_token(session_id, purpose="session")
    return CreateSessionResponse(sessionId=session_id, wsToken=ws_token, status="created")


@router.get("/history", response_model=SessionHistoryListResponse)
def list_session_history() -> SessionHistoryListResponse:
    _refresh_history_from_reports()
    return SessionHistoryListResponse(items=session_history_store.list())


@router.get("/history/{session_id}")
def get_session_history(session_id: str) -> JSONResponse:
    entry = session_history_store.get(session_id)
    if entry is None:
        raise HTTPException(status_code=404, detail="history not found")
    return JSONResponse(entry)


@router.delete("/history/{session_id}")
def delete_session_history(session_id: str) -> JSONResponse:
    deleted = session_history_store.delete(session_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="history not found")
    return JSONResponse({"deleted": True})


@router.get("/{session_id}/report")
def get_session_report(session_id: str) -> JSONResponse:
    record = session_store.get(session_id)
    if record is None or record.report is None:
        # 也尝试从磁盘读取（进程重启容错）
        report = _load_report_from_disk(session_id)
        if report is None:
            raise HTTPException(status_code=404, detail="report not ready")
        if record is not None:
            session_history_store.upsert_from_record(record, report=report)
        else:
            session_history_store.upsert_from_report(report)
        return JSONResponse(report)
    session_history_store.upsert_from_record(record, report=record.report)
    return JSONResponse(record.report)


@router.get("/{session_id}/report/download")
def download_session_report(session_id: str, format: str = "txt"):
    record = session_store.get(session_id)
    report = record.report if record else None
    if report is None:
        report = _load_report_from_disk(session_id)
    if report is None:
        raise HTTPException(status_code=404, detail="report not ready")
    if record is not None:
        session_history_store.upsert_from_record(record, report=report)
    else:
        session_history_store.upsert_from_report(report)

    fmt = format.lower()
    renderers = {"txt": render_txt, "srt": render_srt, "md": render_md}
    base = report.get("sessionName") or session_id
    if fmt == "json":
        import json

        body = json.dumps(report, ensure_ascii=False, indent=2)
        media_type = "application/json"
        ext = "json"
    elif fmt in renderers:
        body = renderers[fmt](report)
        media_type = "application/x-subrip" if fmt == "srt" else "text/plain"
        ext = fmt
    else:
        raise HTTPException(status_code=400, detail="unsupported format")

    filename = _safe_filename(f"{base}.{ext}")
    return PlainTextResponse(
        body,
        media_type=f"{media_type}; charset=utf-8",
        headers={"Content-Disposition": _content_disposition(filename, ext)},
    )


def _safe_filename(name: str) -> str:
    keep = "-_.() "
    cleaned = "".join(c for c in name if c.isalnum() or c in keep or "一" <= c <= "鿿")
    return cleaned.strip() or "report.txt"


def _content_disposition(filename: str, ext: str) -> str:
    """构造兼容中文文件名的 Content-Disposition。

    HTTP 头只能用 latin-1 编码，含中文的文件名直接写 filename="…" 会抛
    UnicodeEncodeError（500）。按 RFC 6266 提供 ASCII 兜底 filename + RFC 5987
    的 filename*（百分号编码 UTF-8），现代浏览器优先用后者还原中文名。
    """
    ascii_fallback = filename.encode("ascii", "ignore").decode("ascii").strip()
    if not ascii_fallback or ascii_fallback in (f".{ext}", ext):
        ascii_fallback = f"report.{ext}"
    quoted = quote(filename, encoding="utf-8")
    return f"attachment; filename=\"{ascii_fallback}\"; filename*=UTF-8''{quoted}"


def _load_report_from_disk(session_id: str) -> dict[str, Any] | None:
    import json

    for path in settings.report_dir.glob(f"{session_id}-report-*.json"):
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
    return None


def _refresh_history_from_reports() -> None:
    import json

    for entry in session_history_store.list():
        report_id = entry.get("reportId")
        if not report_id:
            continue
        path = settings.report_dir / f"{report_id}.json"
        try:
            report = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        session_history_store.upsert_from_report(report)


@router.post(
    "/{session_id}/handoff",
    response_model=IssueHandoffResponse,
    response_model_by_alias=True,
)
def issue_session_handoff(session_id: str, payload: IssueHandoffRequest) -> IssueHandoffResponse:
    ticket = handoff_tokens.issue(
        session_id=session_id,
        source=payload.source,
        source_language=payload.source_language,
        target_language=payload.target_language,
        display_mode=payload.display_mode,
    )
    query = urlencode(
        {
            "sessionId": session_id,
            "source": payload.source or "",
            "sourceLanguage": payload.source_language or "",
            "targetLanguage": payload.target_language or "",
            "displayMode": payload.display_mode,
            "token": ticket.token,
        }
    )
    return IssueHandoffResponse(
        handoffToken=ticket.token,
        expiresAt=ticket.expires_at,
        deepLinkUrl=f"lingosync://floating/start?{query}",
    )


@router.post(
    "/handoff/claim",
    response_model=ClaimHandoffResponse,
    response_model_by_alias=True,
)
def claim_session_handoff(payload: ClaimHandoffRequest) -> ClaimHandoffResponse:
    try:
        claim = handoff_tokens.claim(payload.token)
    except HandoffTokenError as error:
        status_code = {"not_found": 404, "used": 409, "expired": 410}.get(error.code, 400)
        raise HTTPException(
            status_code=status_code, detail=f"handoff token {error.code}"
        ) from error

    return ClaimHandoffResponse(
        sessionId=claim.session_id,
        wsUrl=f"/api/ws/sessions/{claim.session_id}?token={claim.ws_token}",
        wsToken=claim.ws_token,
        source=claim.source,
        sourceLanguage=claim.source_language,
        targetLanguage=claim.target_language,
        displayMode=claim.display_mode,
        expiresAt=claim.expires_at,
    )
