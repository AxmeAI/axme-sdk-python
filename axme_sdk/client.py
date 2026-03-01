from __future__ import annotations

from dataclasses import dataclass
import time
from typing import Any, Callable
from uuid import uuid4

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
    max_retries: int = 2
    retry_backoff_seconds: float = 0.2
    auto_trace_id: bool = True
    default_owner_agent: str | None = None
    mcp_endpoint_path: str = "/mcp"
    mcp_protocol_version: str = "2024-11-05"
    mcp_observer: Callable[[dict[str, Any]], None] | None = None


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
        self._mcp_tool_schemas: dict[str, dict[str, Any]] = {}

    def close(self) -> None:
        if self._owns_http_client:
            self._http.close()

    def __enter__(self) -> "AxmeClient":
        return self

    def __exit__(self, exc_type: Any, exc: Any, traceback: Any) -> None:
        self.close()

    def health(self, *, trace_id: str | None = None) -> dict[str, Any]:
        return self._request_json("GET", "/health", trace_id=trace_id, retryable=True)

    def create_intent(
        self,
        payload: dict[str, Any],
        *,
        correlation_id: str,
        idempotency_key: str | None = None,
        trace_id: str | None = None,
    ) -> dict[str, Any]:
        request_payload = dict(payload)
        existing_correlation_id = request_payload.get("correlation_id")
        if existing_correlation_id is not None and existing_correlation_id != correlation_id:
            raise ValueError("payload correlation_id must match correlation_id argument")
        request_payload["correlation_id"] = correlation_id

        return self._request_json(
            "POST",
            "/v1/intents",
            json_body=request_payload,
            idempotency_key=idempotency_key,
            trace_id=trace_id,
            retryable=idempotency_key is not None,
        )

    def get_intent(self, intent_id: str, *, trace_id: str | None = None) -> dict[str, Any]:
        return self._request_json("GET", f"/v1/intents/{intent_id}", trace_id=trace_id, retryable=True)

    def list_inbox(self, *, owner_agent: str | None = None, trace_id: str | None = None) -> dict[str, Any]:
        params: dict[str, str] | None = None
        if owner_agent is not None:
            params = {"owner_agent": owner_agent}
        return self._request_json("GET", "/v1/inbox", params=params, trace_id=trace_id, retryable=True)

    def get_inbox_thread(self, thread_id: str, *, owner_agent: str | None = None, trace_id: str | None = None) -> dict[str, Any]:
        params: dict[str, str] | None = None
        if owner_agent is not None:
            params = {"owner_agent": owner_agent}
        return self._request_json(
            "GET",
            f"/v1/inbox/{thread_id}",
            params=params,
            trace_id=trace_id,
            retryable=True,
        )

    def list_inbox_changes(
        self,
        *,
        owner_agent: str | None = None,
        cursor: str | None = None,
        limit: int | None = None,
        trace_id: str | None = None,
    ) -> dict[str, Any]:
        params: dict[str, str] = {}
        if owner_agent is not None:
            params["owner_agent"] = owner_agent
        if cursor is not None:
            params["cursor"] = cursor
        if limit is not None:
            params["limit"] = str(limit)
        return self._request_json(
            "GET",
            "/v1/inbox/changes",
            params=params or None,
            trace_id=trace_id,
            retryable=True,
        )

    def reply_inbox_thread(
        self,
        thread_id: str,
        *,
        message: str,
        owner_agent: str | None = None,
        idempotency_key: str | None = None,
        trace_id: str | None = None,
    ) -> dict[str, Any]:
        params: dict[str, str] | None = None
        if owner_agent is not None:
            params = {"owner_agent": owner_agent}
        return self._request_json(
            "POST",
            f"/v1/inbox/{thread_id}/reply",
            params=params,
            json_body={"message": message},
            idempotency_key=idempotency_key,
            trace_id=trace_id,
            retryable=idempotency_key is not None,
        )

    def delegate_inbox_thread(
        self,
        thread_id: str,
        payload: dict[str, Any],
        *,
        owner_agent: str | None = None,
        idempotency_key: str | None = None,
        trace_id: str | None = None,
    ) -> dict[str, Any]:
        params: dict[str, str] | None = None
        if owner_agent is not None:
            params = {"owner_agent": owner_agent}
        return self._request_json(
            "POST",
            f"/v1/inbox/{thread_id}/delegate",
            params=params,
            json_body=payload,
            idempotency_key=idempotency_key,
            trace_id=trace_id,
            retryable=idempotency_key is not None,
        )

    def approve_inbox_thread(
        self,
        thread_id: str,
        payload: dict[str, Any],
        *,
        owner_agent: str | None = None,
        idempotency_key: str | None = None,
        trace_id: str | None = None,
    ) -> dict[str, Any]:
        params: dict[str, str] | None = None
        if owner_agent is not None:
            params = {"owner_agent": owner_agent}
        return self._request_json(
            "POST",
            f"/v1/inbox/{thread_id}/approve",
            params=params,
            json_body=payload,
            idempotency_key=idempotency_key,
            trace_id=trace_id,
            retryable=idempotency_key is not None,
        )

    def reject_inbox_thread(
        self,
        thread_id: str,
        payload: dict[str, Any],
        *,
        owner_agent: str | None = None,
        idempotency_key: str | None = None,
        trace_id: str | None = None,
    ) -> dict[str, Any]:
        params: dict[str, str] | None = None
        if owner_agent is not None:
            params = {"owner_agent": owner_agent}
        return self._request_json(
            "POST",
            f"/v1/inbox/{thread_id}/reject",
            params=params,
            json_body=payload,
            idempotency_key=idempotency_key,
            trace_id=trace_id,
            retryable=idempotency_key is not None,
        )

    def delete_inbox_messages(
        self,
        thread_id: str,
        payload: dict[str, Any],
        *,
        owner_agent: str | None = None,
        idempotency_key: str | None = None,
        trace_id: str | None = None,
    ) -> dict[str, Any]:
        params: dict[str, str] | None = None
        if owner_agent is not None:
            params = {"owner_agent": owner_agent}
        return self._request_json(
            "POST",
            f"/v1/inbox/{thread_id}/messages/delete",
            params=params,
            json_body=payload,
            idempotency_key=idempotency_key,
            trace_id=trace_id,
            retryable=idempotency_key is not None,
        )

    def decide_approval(
        self,
        approval_id: str,
        *,
        decision: str,
        comment: str | None = None,
        idempotency_key: str | None = None,
        trace_id: str | None = None,
    ) -> dict[str, Any]:
        payload: dict[str, Any] = {"decision": decision}
        if comment is not None:
            payload["comment"] = comment
        return self._request_json(
            "POST",
            f"/v1/approvals/{approval_id}/decision",
            json_body=payload,
            idempotency_key=idempotency_key,
            trace_id=trace_id,
            retryable=idempotency_key is not None,
        )

    def get_capabilities(self, *, trace_id: str | None = None) -> dict[str, Any]:
        return self._request_json("GET", "/v1/capabilities", trace_id=trace_id, retryable=True)

    def create_invite(
        self,
        payload: dict[str, Any],
        *,
        idempotency_key: str | None = None,
        trace_id: str | None = None,
    ) -> dict[str, Any]:
        return self._request_json(
            "POST",
            "/v1/invites/create",
            json_body=payload,
            idempotency_key=idempotency_key,
            trace_id=trace_id,
            retryable=idempotency_key is not None,
        )

    def get_invite(self, token: str, *, trace_id: str | None = None) -> dict[str, Any]:
        return self._request_json("GET", f"/v1/invites/{token}", trace_id=trace_id, retryable=True)

    def accept_invite(
        self,
        token: str,
        payload: dict[str, Any],
        *,
        idempotency_key: str | None = None,
        trace_id: str | None = None,
    ) -> dict[str, Any]:
        return self._request_json(
            "POST",
            f"/v1/invites/{token}/accept",
            json_body=payload,
            idempotency_key=idempotency_key,
            trace_id=trace_id,
            retryable=idempotency_key is not None,
        )

    def create_media_upload(
        self,
        payload: dict[str, Any],
        *,
        idempotency_key: str | None = None,
        trace_id: str | None = None,
    ) -> dict[str, Any]:
        return self._request_json(
            "POST",
            "/v1/media/create-upload",
            json_body=payload,
            idempotency_key=idempotency_key,
            trace_id=trace_id,
            retryable=idempotency_key is not None,
        )

    def get_media_upload(self, upload_id: str, *, trace_id: str | None = None) -> dict[str, Any]:
        return self._request_json("GET", f"/v1/media/{upload_id}", trace_id=trace_id, retryable=True)

    def finalize_media_upload(
        self,
        payload: dict[str, Any],
        *,
        idempotency_key: str | None = None,
        trace_id: str | None = None,
    ) -> dict[str, Any]:
        return self._request_json(
            "POST",
            "/v1/media/finalize-upload",
            json_body=payload,
            idempotency_key=idempotency_key,
            trace_id=trace_id,
            retryable=idempotency_key is not None,
        )

    def upsert_schema(
        self,
        payload: dict[str, Any],
        *,
        idempotency_key: str | None = None,
        trace_id: str | None = None,
    ) -> dict[str, Any]:
        return self._request_json(
            "POST",
            "/v1/schemas",
            json_body=payload,
            idempotency_key=idempotency_key,
            trace_id=trace_id,
            retryable=idempotency_key is not None,
        )

    def get_schema(self, semantic_type: str, *, trace_id: str | None = None) -> dict[str, Any]:
        return self._request_json("GET", f"/v1/schemas/{semantic_type}", trace_id=trace_id, retryable=True)

    def register_nick(
        self,
        payload: dict[str, Any],
        *,
        idempotency_key: str | None = None,
        trace_id: str | None = None,
    ) -> dict[str, Any]:
        return self._request_json(
            "POST",
            "/v1/users/register-nick",
            json_body=payload,
            idempotency_key=idempotency_key,
            trace_id=trace_id,
            retryable=idempotency_key is not None,
        )

    def check_nick(self, nick: str, *, trace_id: str | None = None) -> dict[str, Any]:
        return self._request_json("GET", "/v1/users/check-nick", params={"nick": nick}, trace_id=trace_id, retryable=True)

    def rename_nick(
        self,
        payload: dict[str, Any],
        *,
        idempotency_key: str | None = None,
        trace_id: str | None = None,
    ) -> dict[str, Any]:
        return self._request_json(
            "POST",
            "/v1/users/rename-nick",
            json_body=payload,
            idempotency_key=idempotency_key,
            trace_id=trace_id,
            retryable=idempotency_key is not None,
        )

    def get_user_profile(self, owner_agent: str, *, trace_id: str | None = None) -> dict[str, Any]:
        return self._request_json(
            "GET",
            "/v1/users/profile",
            params={"owner_agent": owner_agent},
            trace_id=trace_id,
            retryable=True,
        )

    def update_user_profile(
        self,
        payload: dict[str, Any],
        *,
        idempotency_key: str | None = None,
        trace_id: str | None = None,
    ) -> dict[str, Any]:
        return self._request_json(
            "POST",
            "/v1/users/profile/update",
            json_body=payload,
            idempotency_key=idempotency_key,
            trace_id=trace_id,
            retryable=idempotency_key is not None,
        )

    def upsert_webhook_subscription(
        self,
        payload: dict[str, Any],
        *,
        idempotency_key: str | None = None,
        trace_id: str | None = None,
    ) -> dict[str, Any]:
        return self._request_json(
            "POST",
            "/v1/webhooks/subscriptions",
            json_body=payload,
            idempotency_key=idempotency_key,
            trace_id=trace_id,
            retryable=idempotency_key is not None,
        )

    def list_webhook_subscriptions(self, *, owner_agent: str | None = None, trace_id: str | None = None) -> dict[str, Any]:
        params: dict[str, str] | None = None
        if owner_agent is not None:
            params = {"owner_agent": owner_agent}
        return self._request_json("GET", "/v1/webhooks/subscriptions", params=params, trace_id=trace_id, retryable=True)

    def delete_webhook_subscription(
        self,
        subscription_id: str,
        *,
        owner_agent: str | None = None,
        trace_id: str | None = None,
    ) -> dict[str, Any]:
        params: dict[str, str] | None = None
        if owner_agent is not None:
            params = {"owner_agent": owner_agent}
        return self._request_json(
            "DELETE",
            f"/v1/webhooks/subscriptions/{subscription_id}",
            params=params,
            trace_id=trace_id,
            retryable=True,
        )

    def publish_webhook_event(
        self,
        payload: dict[str, Any],
        *,
        owner_agent: str | None = None,
        idempotency_key: str | None = None,
        trace_id: str | None = None,
    ) -> dict[str, Any]:
        params: dict[str, str] | None = None
        if owner_agent is not None:
            params = {"owner_agent": owner_agent}
        return self._request_json(
            "POST",
            "/v1/webhooks/events",
            params=params,
            json_body=payload,
            idempotency_key=idempotency_key,
            trace_id=trace_id,
            retryable=idempotency_key is not None,
        )

    def replay_webhook_event(
        self,
        event_id: str,
        *,
        owner_agent: str | None = None,
        idempotency_key: str | None = None,
        trace_id: str | None = None,
    ) -> dict[str, Any]:
        params: dict[str, str] | None = None
        if owner_agent is not None:
            params = {"owner_agent": owner_agent}
        response = self._request_json(
            "POST",
            f"/v1/webhooks/events/{event_id}/replay",
            params=params,
            idempotency_key=idempotency_key,
            trace_id=trace_id,
            retryable=idempotency_key is not None,
        )
        return response

    def mcp_initialize(self, *, protocol_version: str | None = None, trace_id: str | None = None) -> dict[str, Any]:
        payload = {
            "jsonrpc": "2.0",
            "id": str(uuid4()),
            "method": "initialize",
            "params": {"protocolVersion": protocol_version or self._config.mcp_protocol_version},
        }
        return self._mcp_request(payload=payload, trace_id=trace_id, retryable=True)

    def mcp_list_tools(self, *, trace_id: str | None = None) -> dict[str, Any]:
        payload = {
            "jsonrpc": "2.0",
            "id": str(uuid4()),
            "method": "tools/list",
            "params": {},
        }
        result = self._mcp_request(payload=payload, trace_id=trace_id, retryable=True)
        tools = result.get("tools")
        if isinstance(tools, list):
            self._mcp_tool_schemas = {}
            for tool in tools:
                if not isinstance(tool, dict):
                    continue
                name = tool.get("name")
                input_schema = tool.get("inputSchema")
                if isinstance(name, str) and isinstance(input_schema, dict):
                    self._mcp_tool_schemas[name] = input_schema
        return result

    def mcp_call_tool(
        self,
        name: str,
        *,
        arguments: dict[str, Any] | None = None,
        owner_agent: str | None = None,
        idempotency_key: str | None = None,
        trace_id: str | None = None,
        validate_input_schema: bool = True,
        retryable: bool | None = None,
    ) -> dict[str, Any]:
        if not isinstance(name, str) or not name.strip():
            raise ValueError("tool name must be non-empty string")
        args = dict(arguments or {})
        resolved_owner = owner_agent or self._config.default_owner_agent
        if resolved_owner and "owner_agent" not in args:
            args["owner_agent"] = resolved_owner
        if idempotency_key and "idempotency_key" not in args:
            args["idempotency_key"] = idempotency_key

        if validate_input_schema:
            self._validate_mcp_tool_arguments(name=name.strip(), arguments=args)

        params: dict[str, Any] = {"name": name.strip(), "arguments": args}
        if resolved_owner:
            params["owner_agent"] = resolved_owner
        payload = {
            "jsonrpc": "2.0",
            "id": str(uuid4()),
            "method": "tools/call",
            "params": params,
        }
        should_retry = retryable if retryable is not None else bool(idempotency_key)
        return self._mcp_request(payload=payload, trace_id=trace_id, retryable=should_retry)

    def _request_json(
        self,
        method: str,
        path: str,
        *,
        params: dict[str, str] | None = None,
        json_body: dict[str, Any] | None = None,
        idempotency_key: str | None = None,
        trace_id: str | None = None,
        retryable: bool,
    ) -> dict[str, Any]:
        headers: dict[str, str] | None = None
        normalized_trace_id = self._normalize_trace_id(trace_id)
        if idempotency_key is not None or normalized_trace_id is not None:
            headers = {}
            if idempotency_key is not None:
                headers["Idempotency-Key"] = idempotency_key
            if normalized_trace_id is not None:
                headers["X-Trace-Id"] = normalized_trace_id

        attempts = 1 + (self._config.max_retries if retryable else 0)
        for attempt_idx in range(attempts):
            try:
                response = self._http.request(
                    method=method,
                    url=path,
                    params=params,
                    json=json_body,
                    headers=headers,
                )
            except (httpx.TimeoutException, httpx.TransportError):
                if attempt_idx >= attempts - 1:
                    raise
                self._sleep_before_retry(attempt_idx, retry_after=None)
                continue

            if retryable and attempt_idx < attempts - 1 and _is_retryable_status(response.status_code):
                retry_after = _parse_retry_after(response.headers.get("Retry-After"))
                self._sleep_before_retry(attempt_idx, retry_after=retry_after)
                continue
            return self._parse_json_response(response)

        raise RuntimeError("unreachable retry loop state")

    def _mcp_request(
        self,
        *,
        payload: dict[str, Any],
        trace_id: str | None,
        retryable: bool,
    ) -> dict[str, Any]:
        self._notify_mcp_observer(
            {
                "phase": "request",
                "method": payload.get("method"),
                "rpc_id": payload.get("id"),
                "retryable": retryable,
            }
        )
        response = self._request_json(
            "POST",
            self._config.mcp_endpoint_path,
            json_body=payload,
            trace_id=trace_id,
            retryable=retryable,
        )
        if isinstance(response.get("error"), dict):
            self._raise_mcp_rpc_error(response)
        result = response.get("result")
        if not isinstance(result, dict):
            raise AxmeHttpError(502, "invalid MCP response: missing result object", body=response)
        self._notify_mcp_observer(
            {
                "phase": "response",
                "method": payload.get("method"),
                "rpc_id": payload.get("id"),
                "result_keys": sorted(result.keys()),
            }
        )
        return result

    def _raise_mcp_rpc_error(self, response_payload: dict[str, Any]) -> None:
        error = response_payload.get("error")
        if not isinstance(error, dict):
            raise AxmeHttpError(502, "invalid MCP response: error is not object", body=response_payload)
        code = error.get("code")
        message = error.get("message")
        if not isinstance(code, int):
            code = -32000
        if not isinstance(message, str) or not message:
            message = "MCP RPC error"
        data = error.get("data")
        kwargs = {"body": {"code": code, "message": message, "data": data}}
        if code in {-32001, -32003}:
            raise AxmeAuthError(403, message, **kwargs)
        if code == -32004:
            raise AxmeRateLimitError(429, message, **kwargs)
        if code == -32602:
            raise AxmeValidationError(422, message, **kwargs)
        if code <= -32000:
            raise AxmeServerError(502, message, **kwargs)
        raise AxmeHttpError(400, message, **kwargs)

    def _validate_mcp_tool_arguments(self, *, name: str, arguments: dict[str, Any]) -> None:
        schema = self._mcp_tool_schemas.get(name)
        if not isinstance(schema, dict):
            return
        required = schema.get("required")
        if isinstance(required, list):
            missing = [item for item in required if isinstance(item, str) and item not in arguments]
            if missing:
                raise ValueError(f"missing required MCP tool arguments for {name}: {', '.join(sorted(missing))}")
        properties = schema.get("properties")
        if not isinstance(properties, dict):
            return
        for key, value in arguments.items():
            if key not in properties:
                continue
            prop = properties[key]
            if not isinstance(prop, dict):
                continue
            declared_type = prop.get("type")
            if isinstance(declared_type, list):
                accepted_types = [item for item in declared_type if isinstance(item, str)]
            elif isinstance(declared_type, str):
                accepted_types = [declared_type]
            else:
                accepted_types = []
            if accepted_types and not _matches_json_type(value=value, accepted_types=accepted_types):
                raise ValueError(f"invalid MCP argument type for {name}.{key}: expected {accepted_types}")

    def _notify_mcp_observer(self, event: dict[str, Any]) -> None:
        observer = self._config.mcp_observer
        if observer is None:
            return
        observer(event)

    def _sleep_before_retry(self, attempt_idx: int, *, retry_after: int | None) -> None:
        if retry_after is not None:
            time.sleep(max(0, retry_after))
            return
        backoff = self._config.retry_backoff_seconds * (2**attempt_idx)
        time.sleep(max(0.0, backoff))

    def _normalize_trace_id(self, trace_id: str | None) -> str | None:
        if trace_id is not None:
            return trace_id
        if self._config.auto_trace_id:
            return str(uuid4())
        return None

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


def _is_retryable_status(status_code: int) -> bool:
    return status_code == 429 or status_code >= 500


def _matches_json_type(*, value: Any, accepted_types: list[str]) -> bool:
    for type_name in accepted_types:
        if type_name == "null" and value is None:
            return True
        if type_name == "string" and isinstance(value, str):
            return True
        if type_name == "boolean" and isinstance(value, bool):
            return True
        if type_name == "integer" and isinstance(value, int) and not isinstance(value, bool):
            return True
        if type_name == "number" and isinstance(value, (int, float)) and not isinstance(value, bool):
            return True
        if type_name == "object" and isinstance(value, dict):
            return True
        if type_name == "array" and isinstance(value, list):
            return True
    return False
