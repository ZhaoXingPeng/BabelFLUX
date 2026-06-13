class DashScopeError(Exception):
    """Base error for DashScope provider failures."""


class DashScopeConfigurationError(DashScopeError):
    """Raised when required DashScope configuration is missing or invalid."""


class DashScopeAPIError(DashScopeError):
    """Raised when DashScope returns an API-level failure."""

    def __init__(
        self,
        message: str,
        *,
        status_code: int | None = None,
        code: str | None = None,
        request_id: str | None = None,
    ) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.code = code
        self.request_id = request_id

