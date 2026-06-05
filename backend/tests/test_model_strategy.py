from app.models.model_strategy import GlossaryTerm, StrategyPlanRequest
from app.services.model_strategy import (
    GUMMY_PROVIDER,
    LIVE_TRANSLATE_PROVIDER,
    QWEN_TTS_PROVIDER,
    build_strategy_plan,
)


def test_auto_strategy_prefers_live_translate_with_glossary() -> None:
    plan = build_strategy_plan(
        StrategyPlanRequest(
            sourceLanguage="en",
            targetLanguage="zh",
            domain="技术",
            glossary=[
                GlossaryTerm(sourceTerm="near win", targetTerm="差一点成功", priority=10),
                GlossaryTerm(sourceTerm="checkpoint", targetTerm="检查点", priority=5),
            ],
        )
    )

    session = plan.live_translate_session["event"]["session"]
    assert plan.primary_provider == LIVE_TRANSLATE_PROVIDER
    assert GUMMY_PROVIDER in plan.fallback_providers
    assert session["modalities"] == ["text"]
    assert session["input_audio_transcription"] == {
        "model": "qwen3-asr-flash-realtime",
        "language": "en",
    }
    assert session["translation"]["language"] == "zh"
    assert session["translation"]["corpus"]["phrases"] == {
        "near win": "差一点成功",
        "checkpoint": "检查点",
    }
    assert "技术" in plan.final_correction_prompt
    assert "near win -> 差一点成功" in plan.final_correction_prompt


def test_strategy_enables_audio_and_tts_provider_when_requested() -> None:
    plan = build_strategy_plan(StrategyPlanRequest(ttsEnabled=True))

    session = plan.live_translate_session["event"]["session"]
    assert session["modalities"] == ["text", "audio"]
    assert session["voice"] == "Cherry"
    assert plan.tts_provider == QWEN_TTS_PROVIDER


def test_gummy_preference_changes_primary_but_keeps_live_translate_fallback() -> None:
    plan = build_strategy_plan(
        StrategyPlanRequest(providerPreference="gummy", sourceLanguage="en", targetLanguage="zh")
    )

    assert plan.primary_provider == GUMMY_PROVIDER
    assert LIVE_TRANSLATE_PROVIDER in plan.fallback_providers
    assert plan.gummy_config == {
        "model": "gummy-realtime-v1",
        "format": "pcm",
        "sample_rate": 16000,
        "source_language": "en",
        "transcription_enabled": True,
        "translation_enabled": True,
        "translation_target_languages": ["zh"],
    }

