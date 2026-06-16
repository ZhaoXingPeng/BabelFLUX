import asyncio
import base64

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile

from app.api.auth import require_model_gateway_auth
from app.core.config import settings
from app.models.model_gateway import (
    ASRSegmentResponse,
    ASRTranscribeResponse,
    LLMGenerateRequest,
    LLMGenerateResponse,
    TTSSynthesizeRequest,
    TTSSynthesizeResponse,
)
from app.models.model_strategy import StrategyPlanRequest, StrategyPlanResponse
from app.services.model_strategy import build_strategy_plan
from app.services.providers.dashscope import (
    DashScopeAPIError,
    DashScopeClient,
    DashScopeConfig,
    DashScopeConfigurationError,
)

router = APIRouter(
    prefix="/models",
    tags=["models"],
    dependencies=[Depends(require_model_gateway_auth)],
)


def get_dashscope_client() -> DashScopeClient:
    return DashScopeClient(DashScopeConfig.from_settings(settings))


def _raise_provider_http_error(error: Exception) -> None:
    if isinstance(error, DashScopeConfigurationError):
        raise HTTPException(status_code=503, detail=str(error)) from error
    if isinstance(error, DashScopeAPIError):
        raise HTTPException(
            status_code=502,
            detail={
                "message": str(error),
                "code": error.code,
                "requestId": error.request_id,
            },
        ) from error
    if isinstance(error, asyncio.TimeoutError):
        raise HTTPException(status_code=504, detail="DashScope request timed out") from error
    raise error


@router.post(
    "/llm/generate",
    response_model=LLMGenerateResponse,
    response_model_by_alias=True,
)
async def generate_llm(
    request: LLMGenerateRequest,
    client: DashScopeClient = Depends(get_dashscope_client),
) -> LLMGenerateResponse:
    try:
        result = await client.generate(
            model=request.model,
            endpoint=request.endpoint,
            messages=[message.model_dump() for message in request.messages],
            parameters=request.parameters,
        )
    except Exception as error:
        _raise_provider_http_error(error)

    return LLMGenerateResponse(
        requestId=result.request_id,
        model=result.model,
        content=result.content,
        contentParts=result.content_parts,
        finishReason=result.finish_reason,
        usage=result.usage,
    )


@router.post(
    "/strategy/plan",
    response_model=StrategyPlanResponse,
    response_model_by_alias=True,
)
def plan_model_strategy(request: StrategyPlanRequest) -> StrategyPlanResponse:
    return build_strategy_plan(request)


@router.post(
    "/asr/transcriptions",
    response_model=ASRTranscribeResponse,
    response_model_by_alias=True,
)
async def transcribe_audio(
    audio: UploadFile = File(...),
    model: str = Form("fun-asr-realtime"),
    audio_format: str = Form("pcm", alias="audioFormat"),
    sample_rate: int = Form(16000, alias="sampleRate"),
    client: DashScopeClient = Depends(get_dashscope_client),
) -> ASRTranscribeResponse:
    audio_bytes = await audio.read()
    if not audio_bytes:
        raise HTTPException(status_code=400, detail="audio file is empty")

    try:
        result = await client.transcribe_audio(
            audio_bytes,
            model=model,
            audio_format=audio_format,
            sample_rate=sample_rate,
        )
    except Exception as error:
        _raise_provider_http_error(error)

    return ASRTranscribeResponse(
        requestId=result.request_id,
        model=result.model,
        text=result.text,
        segments=[
            ASRSegmentResponse(
                text=segment.text,
                startMs=segment.start_ms,
                endMs=segment.end_ms,
                isFinal=segment.is_final,
            )
            for segment in result.segments
        ],
        events=result.events,
        usage=result.usage,
    )


@router.post(
    "/tts/speech",
    response_model=TTSSynthesizeResponse,
    response_model_by_alias=True,
)
async def synthesize_speech(
    request: TTSSynthesizeRequest,
    client: DashScopeClient = Depends(get_dashscope_client),
) -> TTSSynthesizeResponse:
    if not request.text.strip():
        raise HTTPException(status_code=400, detail="text is required")

    try:
        result = await client.synthesize_speech(
            text=request.text,
            model=request.model,
            voice=request.voice,
            language_type=request.language_type,
            audio_format=request.audio_format,
            sample_rate=request.sample_rate,
            mode=request.mode,
        )
    except Exception as error:
        _raise_provider_http_error(error)

    return TTSSynthesizeResponse(
        model=result.model,
        voice=result.voice,
        audioBase64=base64.b64encode(result.audio).decode("ascii"),
        audioBytes=len(result.audio),
        audioFormat=result.audio_format,
        sampleRate=result.sample_rate,
        sessionId=result.session_id,
        events=result.events,
    )
