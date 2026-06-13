from app.models.model_strategy import (
    GlossaryTerm,
    RealtimeRevisionPolicy,
    StrategyPlanRequest,
    StrategyPlanResponse,
)

LIVE_TRANSLATE_PROVIDER = "qwen_live_translate"
GUMMY_PROVIDER = "gummy_realtime"
FUN_ASR_PROVIDER = "fun_asr"
QWEN_TTS_PROVIDER = "qwen_tts"
# 会后完整纠偏模型：经实测，七牛云 marketplace 名（qwen3.7-plus 等）在标准
# dashscope.aliyuncs.com 端点报 "url error"，故选用标准端点实测可用的强模型。
# 可选 qwen3-max / deepseek-v4-pro（均已验证），默认与 .env 的 qwen-plus 一致。
FINAL_CORRECTION_MODEL = "qwen-plus"


DOMAIN_GUIDANCE = {
    "通用": "忠实保留原意，中文表达自然，优先保证字幕短句可读。",
    "技术": "保留 API、框架、模型、论文、产品名和缩写；术语表优先，不把专有名词误译为普通词。",
    "商务": "保留公司名、职位、货币、指标和会议语气，数字与承诺类表述必须谨慎。",
    "教育": "概念解释准确，表达清晰，避免过度口语化。",
    "医疗": "医学术语谨慎，不扩写诊断或治疗建议。",
    "法律": "法律术语准确，不自行解释法条或补充法律结论。",
}


def build_strategy_plan(request: StrategyPlanRequest) -> StrategyPlanResponse:
    primary_provider = _select_primary_provider(request.provider_preference)
    fallback_providers = _fallback_providers(primary_provider)
    realtime_revision_policy = RealtimeRevisionPolicy(
        windowSegments=5,
        windowMs=40_000,
        triggers=[
            "partial_to_final_changed",
            "glossary_term_missing",
            "new_context_changes_previous_meaning",
            "high_risk_number_name_negation",
            "source_sync_recovered",
            "user_glossary_updated",
        ],
        llmEscalationRules=[
            "Only call LLM for high-risk segments inside the revision window.",
            "Prefer deterministic glossary and final-result replacements before LLM.",
            "Do not revise more than the configured per-minute limit.",
        ],
        maxRevisionsPerMinute=6,
    )

    return StrategyPlanResponse(
        primaryProvider=primary_provider,
        fallbackProviders=fallback_providers,
        asrOnlyProvider=FUN_ASR_PROVIDER,
        ttsProvider=QWEN_TTS_PROVIDER if request.tts_enabled else None,
        finalCorrectionModel=FINAL_CORRECTION_MODEL,
        liveTranslateSession=build_live_translate_session(request),
        gummyConfig=build_gummy_config(request),
        realtimeRevisionPolicy=realtime_revision_policy,
        finalCorrectionPrompt=build_final_correction_prompt(request),
    )


def build_live_translate_session(request: StrategyPlanRequest) -> dict[str, object]:
    translation: dict[str, object] = {"language": request.target_language}
    phrases = _glossary_phrases(request.glossary)
    if phrases:
        translation["corpus"] = {"phrases": phrases}

    session: dict[str, object] = {
        "modalities": ["text", "audio"] if request.tts_enabled else ["text"],
        "input_audio_format": "pcm",
        "output_audio_format": "pcm",
        "input_audio_transcription": {
            "model": "qwen3-asr-flash-realtime",
            "language": request.source_language,
        },
        "translation": translation,
    }
    if request.tts_enabled:
        session["voice"] = "Cherry"
    return {
        "model": "qwen3.5-livetranslate-flash-realtime",
        "event": {"type": "session.update", "session": session},
    }


def build_gummy_config(request: StrategyPlanRequest) -> dict[str, object]:
    return {
        "model": "gummy-realtime-v1",
        "format": "pcm",
        "sample_rate": 16000,
        "source_language": request.source_language,
        "transcription_enabled": True,
        "translation_enabled": True,
        "translation_target_languages": [request.target_language],
    }


def build_final_correction_prompt(request: StrategyPlanRequest) -> str:
    guidance = DOMAIN_GUIDANCE.get(request.domain, DOMAIN_GUIDANCE["通用"])
    glossary_lines = _glossary_prompt_lines(request.glossary)
    glossary_block = "\n".join(glossary_lines) if glossary_lines else "无"
    return "\n".join(
        [
            "你是 BabelFlux / 巴别流 同传的最终全文纠偏模块。",
            f"领域：{request.domain}",
            f"源语言：{request.source_language}",
            f"目标语言：{request.target_language}",
            f"领域策略：{guidance}",
            "任务：基于完整源文、实时中文字幕、实时修正记录和术语表，生成最终双语稿和修正记录。",
            "硬性规则：不得扩写原意；不得删除时间轴；术语表优先；只修正影响理解、术语一致性或明显错误的内容。",
            (
                "输出必须是 JSON，字段包括 finalTranscript、finalTranslation、"
                "finalRevisions、glossaryHits、summary、qualityNotes。"
            ),
            "术语表：",
            glossary_block,
        ]
    )


def _select_primary_provider(preference: str) -> str:
    if preference == "gummy":
        return GUMMY_PROVIDER
    if preference == "fun_asr":
        return FUN_ASR_PROVIDER
    return LIVE_TRANSLATE_PROVIDER


def _fallback_providers(primary_provider: str) -> list[str]:
    candidates = [LIVE_TRANSLATE_PROVIDER, GUMMY_PROVIDER, FUN_ASR_PROVIDER]
    return [provider for provider in candidates if provider != primary_provider]


def _glossary_phrases(glossary: list[GlossaryTerm]) -> dict[str, str]:
    return {
        term.source_term: term.target_term
        for term in sorted(glossary, key=lambda item: item.priority, reverse=True)
        if term.source_term and term.target_term
    }


def _glossary_prompt_lines(glossary: list[GlossaryTerm]) -> list[str]:
    lines = []
    for term in sorted(glossary, key=lambda item: item.priority, reverse=True):
        note = f"；备注：{term.note}" if term.note else ""
        lines.append(f"- {term.source_term} -> {term.target_term}；优先级：{term.priority}{note}")
    return lines
