from __future__ import annotations

from typing import Any


class AxmeError(Exception):
    """Base SDK exception."""


class AxmeHttpError(AxmeError):
    """Raised for non-success Axme API responses."""

    def __init__(
        self,
        status_code: int,
        message: str,
        *,
        body: Any | None = None,
        request_id: str | None = None,
        trace_id: str | None = None,
        retry_after: int | None = None,
    ) -> None:
        super().__init__(f"HTTP {status_code}: {message}")
        self.status_code = status_code
        self.message = message
        self.body = body
        self.request_id = request_id
        self.trace_id = trace_id
        self.retry_after = retry_after


class AxmeAuthError(AxmeHttpError):
    """Authentication or authorization failure."""


class AxmeValidationError(AxmeHttpError):
    """Request/contract validation failure."""


class AxmeRateLimitError(AxmeHttpError):
    """Rate limit exceeded."""


class AxmeServerError(AxmeHttpError):
    """Unexpected server-side failure."""
