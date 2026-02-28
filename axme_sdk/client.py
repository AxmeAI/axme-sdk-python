from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import httpx

from .exceptions import (
    AxmeAuthError,
    AxmeHttpError,
    AxmeRateLimitError,
    AxmeServerError,
    AxmeValidationError,
)


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
        return self._parse_json_response(response)

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
        return self._parse_json_response(response)

    def list_inbox(self, *, owner_agent: str | None = None) -> dict[str, Any]:
        params: dict[str, str] | None = None
        if owner_agent is not None:
            params = {"owner_agent": owner_agent}
        response = self._http.get("/v1/inbox", params=params)
        return self._parse_json_response(response)

    def get_inbox_thread(self, thread_id: str, *, owner_agent: str | None = None) -> dict[str, Any]:
        params: dict[str, str] | None = None
        if owner_agent is not None:
            params = {"owner_agent": owner_agent}
        response = self._http.get(f"/v1/inbox/{thread_id}", params=params)
        return self._parse_json_response(response)

    def list_inbox_changes(
        self,
        *,
        owner_agent: str | None = None,
        cursor: str | None = None,
        limit: int | None = None,
    ) -> dict[str, Any]:
        params: dict[str, str] = {}
        if owner_agent is not None:
            params["owner_agent"] = owner_agent
        if cursor is not None:
            params["cursor"] = cursor
        if limit is not None:
            params["limit"] = str(limit)
        response = self._http.get("/v1/inbox/changes", params=params or None)
        return self._parse_json_response(response)

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
        return self._parse_json_response(response)

    def upsert_webhook_subscription(
        self,
        payload: dict[str, Any],
        *,
        idempotency_key: str | None = None,
    ) -> dict[str, Any]:
        headers: dict[str, str] | None = None
        if idempotency_key is not None:
            headers = {"Idempotency-Key": idempotency_key}
        response = self._http.post("/v1/webhooks/subscriptions", json=payload, headers=headers)
        return self._parse_json_response(response)

    def list_webhook_subscriptions(self, *, owner_agent: str | None = None) -> dict[str, Any]:
        params: dict[str, str] | None = None
        if owner_agent is not None:
            params = {"owner_agent": owner_agent}
        response = self._http.get("/v1/webhooks/subscriptions", params=params)
        return self._parse_json_response(response)

    def delete_webhook_subscription(self, subscription_id: str, *, owner_agent: str | None = None) -> dict[str, Any]:
        params: dict[str, str] | None = None
        if owner_agent is not None:
            params = {"owner_agent": owner_agent}
        response = self._http.delete(f"/v1/webhooks/subscriptions/{subscription_id}", params=params)
        return self._parse_json_response(response)

    def publish_webhook_event(self, payload: dict[str, Any], *, owner_agent: str | None = None) -> dict[str, Any]:
        params: dict[str, str] | None = None
        if owner_agent is not None:
            params = {"owner_agent": owner_agent}
        response = self._http.post("/v1/webhooks/events", params=params, json=payload)
        return self._parse_json_response(response)

    def replay_webhook_event(self, event_id: str, *, owner_agent: str | None = None) -> dict[str, Any]:
        params: dict[str, str] | None = None
        if owner_agent is not None:
            params = {"owner_agent": owner_agent}
        response = self._http.post(f"/v1/webhooks/events/{event_id}/replay", params=params)
        return self._parse_json_response(response)

    def _parse_json_response(self, response: httpx.Response) -> dict[str, Any]:
        if response.status_code >= 400:
            self._raise_http_error(response)
        return response.json()

    def _raise_http_error(self, response: httpx.Response) -> None:
        body: Any | None
        body = None
        message = response.text
        try:
            body = response.json()
        except ValueError:
            body = None
        else:
            if isinstance(body, dict):
                error_value = body.get("error")
                if isinstance(error_value, str):
                    message = error_value
                elif isinstance(error_value, dict) and isinstance(error_value.get("message"), str):
                    message = error_value["message"]
                elif isinstance(body.get("message"), str):
                    message = body["message"]
            elif isinstance(body, str):
                message = body

        retry_after = _parse_retry_after(response.headers.get("Retry-After"))
        kwargs = {
            "body": body,
            "request_id": response.headers.get("x-request-id") or response.headers.get("request-id"),
            "trace_id": response.headers.get("x-trace-id") or response.headers.get("trace-id"),
            "retry_after": retry_after,
        }
        status_code = response.status_code
        if status_code in (401, 403):
            raise AxmeAuthError(status_code, message, **kwargs)
        if status_code in (400, 409, 413, 422):
            raise AxmeValidationError(status_code, message, **kwargs)
        if status_code == 429:
            raise AxmeRateLimitError(status_code, message, **kwargs)
        if status_code >= 500:
            raise AxmeServerError(status_code, message, **kwargs)
        raise AxmeHttpError(status_code, message, **kwargs)


def _parse_retry_after(value: str | None) -> int | None:
    if value is None:
        return None
    try:
        return int(value)
    except ValueError:
        return None
