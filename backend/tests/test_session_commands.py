import json

import pytest

from app.services.session_commands import (
    parse_client_payload,
    parse_clock_ms,
    parse_session_overrides,
)


def test_parse_client_payload_accepts_only_json_objects() -> None:
    payload, error = parse_client_payload(json.dumps({"type": "pause_session"}))

    assert payload == {"type": "pause_session"}
    assert error is None

    payload, error = parse_client_payload(json.dumps(["pause_session"]))

    assert payload is None
    assert error == "客户端消息必须是 JSON 对象"


@pytest.mark.parametrize(
    ("value", "expected"),
    [(None, 0), (0, 0), (1234, 1234), (True, None), (-1, None), (1.5, None)],
)
def test_parse_clock_ms_accepts_only_non_negative_integers(
    value: object, expected: int | None
) -> None:
    assert parse_clock_ms(value) == expected


def test_parse_session_overrides_normalizes_values_without_mutating_payload() -> None:
    payload = {
        "sourceLanguage": " en ",
        "targetLanguage": "zh",
        "domain": "技术",
        "inputMode": "url",
        "sourceUrl": " https://example.com/live ",
        "modelProfile": "智能默认",
        "ignored": {"nested": True},
    }
    original = payload.copy()

    overrides, error = parse_session_overrides(payload)

    assert error is None
    assert overrides is not None
    assert overrides.as_record_updates() == {
        "source_language": "en",
        "target_language": "zh",
        "domain": "技术",
        "input_mode": "url",
        "source_url": "https://example.com/live",
        "model_profile": "智能默认",
    }
    assert payload == original


@pytest.mark.parametrize(
    ("field", "value", "message"),
    [
        ("inputMode", "unsupported", "start_session 的 inputMode 不受支持"),
        ("inputMode", 42, "start_session 的 inputMode 必须是非空字符串"),
        ("sourceLanguage", " ", "start_session 的 sourceLanguage 必须是非空字符串"),
        (
            "sourceUrl",
            "ftp://example.com/live",
            "start_session 的 sourceUrl 必须是有效的 http 或 https URL",
        ),
    ],
)
def test_parse_session_overrides_rejects_invalid_values(
    field: str,
    value: object,
    message: str,
) -> None:
    overrides, error = parse_session_overrides({field: value})

    assert overrides is None
    assert error == message
