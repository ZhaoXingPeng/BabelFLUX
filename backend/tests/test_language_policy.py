from app.services.language_policy import (
    infer_source_language,
    initial_provider_source_language,
    should_preflight_language,
    suggest_language_pair,
)


def test_infer_source_language_requires_a_signal() -> None:
    assert infer_source_language("hi there") is None
    assert infer_source_language("hello from the service") == "en"
    assert infer_source_language("这是一个中文样本") == "zh"


def test_mixed_language_samples_follow_dominance_policy() -> None:
    assert infer_source_language("API 网关") is None
    assert infer_source_language("API 网关服务已经上线") == "zh"
    assert infer_source_language("The API 网关 service is ready") == "en"


def test_auto_language_pair_policy_keeps_source_and_target_distinct() -> None:
    assert initial_provider_source_language("auto", "zh") == "en"
    assert initial_provider_source_language("auto", "en") == "zh"
    assert initial_provider_source_language("auto", "ja") == "en"
    assert suggest_language_pair("en", "en") == ("en", "zh")
    assert suggest_language_pair("zh", "en") == ("zh", "en")
    assert should_preflight_language("auto", "zh")
    assert not should_preflight_language("en", "zh")
