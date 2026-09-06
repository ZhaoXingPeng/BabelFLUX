"""Select the concrete models used by a session's user-facing profile."""

from __future__ import annotations

from dataclasses import dataclass

from app.core.config import Settings

DEFAULT_MODEL_PROFILE = "智能默认"
FAST_MODEL_PROFILE = "快速低延迟"
ACCURATE_MODEL_PROFILE = "高准确"
COST_MODEL_PROFILE = "成本优先"
CUSTOM_MODEL_PROFILE = "指定供应商"


@dataclass(frozen=True)
class ModelSelection:
    """Resolved model names kept separate from request/UI labels."""

    profile: str
    live_translate_model: str
    live_translate_asr_model: str
    realtime_revision_model: str
    final_correction_model: str


def select_model_profile(profile: str | None, settings: Settings) -> ModelSelection:
    """Resolve a profile while retaining environment-configured model defaults.

    Only models already supported by the active DashScope adapter are selected here.
    Provider switching remains an explicit future extension rather than an implicit
    fallback that could silently change protocol behavior.
    """

    requested = (profile or DEFAULT_MODEL_PROFILE).strip()
    if requested == FAST_MODEL_PROFILE:
        realtime_revision_model = settings.fast_realtime_revision_model
        final_correction_model = settings.fast_final_correction_model
    elif requested == ACCURATE_MODEL_PROFILE:
        realtime_revision_model = settings.accurate_realtime_revision_model
        final_correction_model = settings.accurate_final_correction_model
    elif requested == COST_MODEL_PROFILE:
        realtime_revision_model = settings.cost_realtime_revision_model
        final_correction_model = settings.cost_final_correction_model
    else:
        requested = (
            requested
            if requested in {DEFAULT_MODEL_PROFILE, CUSTOM_MODEL_PROFILE}
            else DEFAULT_MODEL_PROFILE
        )
        realtime_revision_model = settings.realtime_revision_model
        final_correction_model = settings.final_correction_model

    return ModelSelection(
        profile=requested,
        live_translate_model=settings.live_translate_model,
        live_translate_asr_model=settings.live_translate_asr_model,
        realtime_revision_model=realtime_revision_model,
        final_correction_model=final_correction_model,
    )
