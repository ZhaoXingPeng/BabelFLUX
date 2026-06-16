from fastapi import Header, HTTPException, Query

from app.core.config import settings
from app.services.handoff import handoff_tokens


def _extract_bearer_token(authorization: str | None) -> str | None:
    if not authorization:
        return None
    scheme, _, token = authorization.partition(" ")
    if scheme.lower() != "bearer" or not token.strip():
        return None
    return token.strip()


def require_model_gateway_auth(
    token: str | None = Query(default=None),
    authorization: str | None = Header(default=None),
) -> None:
    if not settings.require_model_gateway_auth:
        return

    candidate = token or _extract_bearer_token(authorization)
    if not candidate or not handoff_tokens.validate_any_session_token(candidate):
        raise HTTPException(status_code=401, detail="model gateway authentication required")
