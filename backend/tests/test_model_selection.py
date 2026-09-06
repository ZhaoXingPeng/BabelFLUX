from app.core.config import Settings
from app.services.model_selection import (
    ACCURATE_MODEL_PROFILE,
    COST_MODEL_PROFILE,
    DEFAULT_MODEL_PROFILE,
    FAST_MODEL_PROFILE,
    select_model_profile,
)
from app.services.pipeline import InterpretationPipeline
from app.services.session_store import SessionRecord


def test_model_profiles_resolve_configured_correction_models() -> None:
    settings = Settings(
        dashscope_api_key="sk-test",
        realtime_revision_model="default-revision",
        final_correction_model="default-final",
        fast_realtime_revision_model="fast-revision",
        fast_final_correction_model="fast-final",
        accurate_realtime_revision_model="accurate-revision",
        accurate_final_correction_model="accurate-final",
        cost_realtime_revision_model="cost-revision",
        cost_final_correction_model="cost-final",
    )

    assert (
        select_model_profile(DEFAULT_MODEL_PROFILE, settings).realtime_revision_model
        == "default-revision"
    )
    assert (
        select_model_profile(FAST_MODEL_PROFILE, settings).final_correction_model
        == "fast-final"
    )
    assert (
        select_model_profile(ACCURATE_MODEL_PROFILE, settings).realtime_revision_model
        == "accurate-revision"
    )
    assert (
        select_model_profile(COST_MODEL_PROFILE, settings).final_correction_model
        == "cost-final"
    )


def test_unknown_model_profile_falls_back_to_safe_defaults() -> None:
    settings = Settings(
        realtime_revision_model="default-revision",
        final_correction_model="default-final",
    )

    selection = select_model_profile("unsupported", settings)

    assert selection.profile == DEFAULT_MODEL_PROFILE
    assert selection.realtime_revision_model == "default-revision"
    assert selection.final_correction_model == "default-final"


def test_pipeline_uses_the_selected_revision_model() -> None:
    settings = Settings(
        dashscope_api_key="sk-test",
        realtime_revision_model="default-revision",
        accurate_realtime_revision_model="accurate-revision",
    )
    pipeline = InterpretationPipeline(
        settings=settings,
        record=SessionRecord(session_id="profile", model_profile=ACCURATE_MODEL_PROFILE),
        emit=lambda _event: None,
    )

    assert pipeline._reviser.model == "accurate-revision"
