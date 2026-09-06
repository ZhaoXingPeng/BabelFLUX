"""Pure validation helpers for commands received through a session WebSocket."""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any
from urllib.parse import urlparse

SESSION_INPUT_MODES = frozenset(
    {
        "demo",
        "url",
        "microphone",
        "browser_audio",
        "screen_window",
        "media_element_audio",
        "system_audio",
    }
)


@dataclass(frozen=True)
class SessionOverrides:
    """Validated values that a ``start_session`` command may override."""

    source_language: str | None = None
    target_language: str | None = None
    domain: str | None = None
    input_mode: str | None = None
    source_url: str | None = None
    model_profile: str | None = None

    def as_record_updates(self) -> dict[str, str]:
        updates = {
            "source_language": self.source_language,
            "target_language": self.target_language,
            "domain": self.domain,
            "input_mode": self.input_mode,
            "source_url": self.source_url,
            "model_profile": self.model_profile,
        }
        return {key: value for key, value in updates.items() if value is not None}


def parse_client_payload(text: str) -> tuple[dict[str, Any] | None, str | None]:
    payload = json.loads(text)
    if not isinstance(payload, dict):
        return None, "客户端消息必须是 JSON 对象"
    return payload, None


def parse_clock_ms(value: Any) -> int | None:
    if value is None:
        return 0
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        return None
    return value


def parse_session_overrides(
    payload: dict[str, Any],
) -> tuple[SessionOverrides | None, str | None]:
    values: dict[str, str] = {}
    fields = {
        "sourceLanguage": "source_language",
        "targetLanguage": "target_language",
        "domain": "domain",
        "inputMode": "input_mode",
        "sourceUrl": "source_url",
        "modelProfile": "model_profile",
    }
    for key, attribute in fields.items():
        if key not in payload or payload[key] is None:
            continue
        value = payload[key]
        if not isinstance(value, str) or not value.strip():
            return None, f"start_session 的 {key} 必须是非空字符串"
        values[attribute] = value.strip()

    input_mode = values.get("input_mode")
    if input_mode is not None and input_mode not in SESSION_INPUT_MODES:
        return None, "start_session 的 inputMode 不受支持"

    source_url = values.get("source_url")
    if source_url is not None:
        parsed = urlparse(source_url)
        if parsed.scheme not in {"http", "https"} or not parsed.netloc:
            return None, "start_session 的 sourceUrl 必须是有效的 http 或 https URL"

    return SessionOverrides(**values), None
