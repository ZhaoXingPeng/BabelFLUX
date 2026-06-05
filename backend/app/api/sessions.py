from typing import Literal
from uuid import uuid4

from fastapi import APIRouter
from pydantic import BaseModel, Field

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


class CreateSessionResponse(BaseModel):
    session_id: str = Field(alias="sessionId")
    status: str


@router.post("", response_model=CreateSessionResponse, response_model_by_alias=True)
def create_session(_: CreateSessionRequest) -> CreateSessionResponse:
    return CreateSessionResponse(sessionId=str(uuid4()), status="created")
