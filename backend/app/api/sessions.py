from datetime import datetime
from typing import Literal
from urllib.parse import urlencode
from uuid import uuid4

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from app.services.handoff import DisplayMode, HandoffTokenError, handoff_tokens

router = APIRouter(prefix="/sessions", tags=["sessions"])


class CreateSessionRequest(BaseModel):
    input_mode: Literal[
        "demo",
        "upload_video",
        "upload_audio",
        "url",
        "microphone",
        "browser_audio",
        "screen_window",
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


class CreateSessionResponse(BaseModel):
    session_id: str = Field(alias="sessionId")
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


@router.post("", response_model=CreateSessionResponse, response_model_by_alias=True)
def create_session(_: CreateSessionRequest) -> CreateSessionResponse:
    return CreateSessionResponse(sessionId=str(uuid4()), status="created")


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
        raise HTTPException(status_code=status_code, detail=f"handoff token {error.code}") from error

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
