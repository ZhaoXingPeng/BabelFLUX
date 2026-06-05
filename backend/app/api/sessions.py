from uuid import uuid4

from fastapi import APIRouter
from pydantic import BaseModel, Field

router = APIRouter(prefix="/sessions", tags=["sessions"])


class CreateSessionRequest(BaseModel):
    input_mode: str = Field(default="demo", alias="inputMode")
    source_language: str = Field(default="en", alias="sourceLanguage")
    target_language: str = Field(default="zh", alias="targetLanguage")


class CreateSessionResponse(BaseModel):
    session_id: str = Field(alias="sessionId")
    status: str


@router.post("", response_model=CreateSessionResponse, response_model_by_alias=True)
def create_session(_: CreateSessionRequest) -> CreateSessionResponse:
    return CreateSessionResponse(sessionId=str(uuid4()), status="created")
