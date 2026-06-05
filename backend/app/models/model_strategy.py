from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


class StrategyModel(BaseModel):
    model_config = ConfigDict(populate_by_name=True)


class GlossaryTerm(StrategyModel):
    source_term: str = Field(alias="sourceTerm")
    target_term: str = Field(alias="targetTerm")
    domain: str | None = None
    priority: int = 0
    note: str | None = None


class StrategyPlanRequest(StrategyModel):
    source_language: str = Field(default="en", alias="sourceLanguage")
    target_language: str = Field(default="zh", alias="targetLanguage")
    domain: str = "通用"
    tts_enabled: bool = Field(default=False, alias="ttsEnabled")
    provider_preference: Literal["auto", "live_translate", "gummy", "fun_asr"] = Field(
        default="auto",
        alias="providerPreference",
    )
    glossary: list[GlossaryTerm] = Field(default_factory=list)


class RealtimeRevisionPolicy(StrategyModel):
    window_segments: int = Field(alias="windowSegments")
    window_ms: int = Field(alias="windowMs")
    triggers: list[str]
    llm_escalation_rules: list[str] = Field(alias="llmEscalationRules")
    max_revisions_per_minute: int = Field(alias="maxRevisionsPerMinute")


class StrategyPlanResponse(StrategyModel):
    primary_provider: str = Field(alias="primaryProvider")
    fallback_providers: list[str] = Field(alias="fallbackProviders")
    asr_only_provider: str = Field(alias="asrOnlyProvider")
    tts_provider: str | None = Field(default=None, alias="ttsProvider")
    final_correction_model: str = Field(alias="finalCorrectionModel")
    live_translate_session: dict[str, Any] = Field(alias="liveTranslateSession")
    gummy_config: dict[str, Any] = Field(alias="gummyConfig")
    realtime_revision_policy: RealtimeRevisionPolicy = Field(alias="realtimeRevisionPolicy")
    final_correction_prompt: str = Field(alias="finalCorrectionPrompt")

