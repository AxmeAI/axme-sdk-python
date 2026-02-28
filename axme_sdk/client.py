from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import httpx

from .exceptions import AxmeHttpError


@dataclass(frozen=True)
class AxmeClientConfig:
    base_url: str
    api_key: str
    timeout_seconds: float = 15.0


class AxmeClient:
    def __init__(self, config: AxmeClientConfig, *, http_client: httpx.Client | None = None) -> None:
        self._config = config
        self._owns_http_client = http_client is None
        self._http = http_client or httpx.Client(
            base_url=self._config.base_url.rstrip("/"),
            timeout=self._config.timeout_seconds,
            headers={
                "Authorization": f"Bearer {self._config.api_key}",
                "Content-Type": "application/json",
            },
        )

    def close(self) -> None:
        if self._owns_http_client:
            self._http.close()

    def __enter__(self) -> "AxmeClient":
        return self

    def __exit__(self, exc_type: Any, exc: Any, traceback: Any) -> None:
        self.close()

    def health(self) -> dict[str, Any]:
        response = self._http.get("/health")
        if response.status_code >= 400:
            raise AxmeHttpError(response.status_code, response.text)
        return response.json()

    def create_intent(
        self,
        payload: dict[str, Any],
        *,
        correlation_id: str,
        idempotency_key: str | None = None,
    ) -> dict[str, Any]:
        request_payload = dict(payload)
        existing_correlation_id = request_payload.get("correlation_id")
        if existing_correlation_id is not None and existing_correlation_id != correlation_id:
            raise ValueError("payload correlation_id must match correlation_id argument")
        request_payload["correlation_id"] = correlation_id

        headers: dict[str, str] | None = None
        if idempotency_key is not None:
            headers = {"Idempotency-Key": idempotency_key}

        response = self._http.post("/v1/intents", json=request_payload, headers=headers)
        if response.status_code >= 400:
            raise AxmeHttpError(response.status_code, response.text)
        return response.json()

    def list_inbox(self, *, owner_agent: str | None = None) -> dict[str, Any]:
        params: dict[str, str] | None = None
        if owner_agent is not None:
            params = {"owner_agent": owner_agent}
        response = self._http.get("/v1/inbox", params=params)
        if response.status_code >= 400:
            raise AxmeHttpError(response.status_code, response.text)
        return response.json()

    def get_inbox_thread(self, thread_id: str, *, owner_agent: str | None = None) -> dict[str, Any]:
        params: dict[str, str] | None = None
        if owner_agent is not None:
            params = {"owner_agent": owner_agent}
        response = self._http.get(f"/v1/inbox/{thread_id}", params=params)
        if response.status_code >= 400:
            raise AxmeHttpError(response.status_code, response.text)
        return response.json()

    def reply_inbox_thread(
        self,
        thread_id: str,
        *,
        message: str,
        owner_agent: str | None = None,
        idempotency_key: str | None = None,
    ) -> dict[str, Any]:
        params: dict[str, str] | None = None
        if owner_agent is not None:
            params = {"owner_agent": owner_agent}
        headers: dict[str, str] | None = None
        if idempotency_key is not None:
            headers = {"Idempotency-Key": idempotency_key}
        response = self._http.post(
            f"/v1/inbox/{thread_id}/reply",
            params=params,
            json={"message": message},
            headers=headers,
        )
        if response.status_code >= 400:
            raise AxmeHttpError(response.status_code, response.text)
        return response.json()
