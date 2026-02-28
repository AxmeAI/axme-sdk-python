from __future__ import annotations


class AxmeError(Exception):
    """Base SDK exception."""


class AxmeHttpError(AxmeError):
    """Raised for non-success Axme API responses."""

    def __init__(self, status_code: int, message: str) -> None:
        super().__init__(f"HTTP {status_code}: {message}")
        self.status_code = status_code
        self.message = message
