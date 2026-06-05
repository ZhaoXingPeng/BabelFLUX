from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import UTC, datetime, timedelta
from secrets import token_urlsafe
from typing import Literal

DisplayMode = Literal["bilingual", "translation-only", "floating", "compact"]


class HandoffTokenError(ValueError):
    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


@dataclass(frozen=True)
class HandoffTicket:
    token: str
    session_id: str
    source: str | None
    source_language: str | None
    target_language: str | None
    display_mode: DisplayMode
    expires_at: datetime
    used: bool = False


@dataclass(frozen=True)
class ClaimedHandoff:
    session_id: str
    ws_token: str
    source: str | None
    source_language: str | None
    target_language: str | None
    display_mode: DisplayMode
    expires_at: datetime


class HandoffTokenStore:
    def __init__(self) -> None:
        self._tickets: dict[str, HandoffTicket] = {}
        self._ws_tokens: dict[str, tuple[str, datetime]] = {}

    def issue(
        self,
        *,
        session_id: str,
        source: str | None,
        source_language: str | None,
        target_language: str | None,
        display_mode: DisplayMode,
        ttl_seconds: int = 60,
    ) -> HandoffTicket:
        self._cleanup()
        token = f"h_{token_urlsafe(24)}"
        ticket = HandoffTicket(
            token=token,
            session_id=session_id,
            source=source,
            source_language=source_language,
            target_language=target_language,
            display_mode=display_mode,
            expires_at=datetime.now(UTC) + timedelta(seconds=ttl_seconds),
        )
        self._tickets[token] = ticket
        return ticket

    def claim(self, token: str) -> ClaimedHandoff:
        self._cleanup()
        ticket = self._tickets.get(token)
        if ticket is None:
            raise HandoffTokenError("not_found")
        if ticket.used:
            raise HandoffTokenError("used")
        if ticket.expires_at <= datetime.now(UTC):
            del self._tickets[token]
            raise HandoffTokenError("expired")

        self._tickets[token] = replace(ticket, used=True)

        ws_token = f"w_{token_urlsafe(24)}"
        self._ws_tokens[ws_token] = (ticket.session_id, ticket.expires_at)
        return ClaimedHandoff(
            session_id=ticket.session_id,
            ws_token=ws_token,
            source=ticket.source,
            source_language=ticket.source_language,
            target_language=ticket.target_language,
            display_mode=ticket.display_mode,
            expires_at=ticket.expires_at,
        )

    def validate_ws_token(self, session_id: str, token: str) -> bool:
        self._cleanup()
        value = self._ws_tokens.get(token)
        if value is None:
            return False
        token_session_id, expires_at = value
        return token_session_id == session_id and expires_at > datetime.now(UTC)

    def reset(self) -> None:
        self._tickets.clear()
        self._ws_tokens.clear()

    def _cleanup(self) -> None:
        now = datetime.now(UTC)
        expired_tickets = [
            token for token, ticket in self._tickets.items() if ticket.expires_at <= now
        ]
        for token in expired_tickets:
            del self._tickets[token]

        expired_ws_tokens = [
            token for token, (_, expires_at) in self._ws_tokens.items() if expires_at <= now
        ]
        for token in expired_ws_tokens:
            del self._ws_tokens[token]


handoff_tokens = HandoffTokenStore()
