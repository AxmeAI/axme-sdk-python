from __future__ import annotations

import json

import httpx
import pytest

from axme_sdk import AxmeClient, AxmeClientConfig
from axme_sdk.exceptions import AxmeHttpError


def _transport(handler):
    return httpx.MockTransport(handler)


def _client(handler, api_key: str = "token") -> AxmeClient:
    cfg = AxmeClientConfig(base_url="https://api.axme.test", api_key=api_key)
    http_client = httpx.Client(
        transport=_transport(handler),
        base_url=cfg.base_url,
        headers={
            "Authorization": f"Bearer {cfg.api_key}",
            "Content-Type": "application/json",
        },
    )
    return AxmeClient(cfg, http_client=http_client)


def _thread_payload() -> dict[str, object]:
    return {
        "thread_id": "11111111-1111-4111-8111-111111111111",
        "intent_id": "22222222-2222-4222-8222-222222222222",
        "status": "active",
        "owner_agent": "agent://owner",
        "from_agent": "agent://from",
        "to_agent": "agent://to",
        "created_at": "2026-02-28T00:00:00Z",
        "updated_at": "2026-02-28T00:00:01Z",
        "timeline": [
            {
                "event_id": "33333333-3333-4333-8333-333333333333",
                "event_type": "message.sent",
                "actor": "gateway",
                "at": "2026-02-28T00:00:01Z",
                "details": {"message": "hello"},
            }
        ],
    }


def test_health_success() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.method == "GET"
        assert request.url.path == "/health"
        assert request.headers["Authorization"] == "Bearer token"
        return httpx.Response(200, json={"ok": True})

    client = _client(handler)
    assert client.health() == {"ok": True}


def test_create_intent_success() -> None:
    payload = {
        "intent_type": "notify.message.v1",
        "to_agent": "agent://user/test",
        "from_agent": "agent://user/self",
        "payload": {"text": "hello"},
    }

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.method == "POST"
        assert request.url.path == "/v1/intents"
        body = json.loads(request.read().decode("utf-8"))
        assert body["correlation_id"] == "11111111-1111-1111-1111-111111111111"
        assert body["intent_type"] == "notify.message.v1"
        assert request.headers["idempotency-key"] == "idem-1"
        return httpx.Response(200, json={"intent_id": "it_123"})

    client = _client(handler)
    assert (
        client.create_intent(
            payload,
            correlation_id="11111111-1111-1111-1111-111111111111",
            idempotency_key="idem-1",
        )
        == {"intent_id": "it_123"}
    )


def test_create_intent_raises_http_error() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(401, text="unauthorized")

    client = _client(handler, api_key="bad-token")

    with pytest.raises(AxmeHttpError) as exc_info:
        client.create_intent(
            {"intent_type": "notify.message.v1", "to_agent": "agent://x", "from_agent": "agent://y", "payload": {}},
            correlation_id="11111111-1111-1111-1111-111111111111",
        )

    assert exc_info.value.status_code == 401


def test_create_intent_raises_for_mismatched_correlation_id() -> None:
    client = _client(lambda request: httpx.Response(200, json={"intent_id": "it_123"}))

    with pytest.raises(ValueError, match="payload correlation_id"):
        client.create_intent(
            {
                "intent_type": "notify.message.v1",
                "to_agent": "agent://x",
                "from_agent": "agent://y",
                "payload": {},
                "correlation_id": "22222222-2222-2222-2222-222222222222",
            },
            correlation_id="11111111-1111-1111-1111-111111111111",
        )


def test_list_inbox_success() -> None:
    thread = _thread_payload()

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.method == "GET"
        assert request.url.path == "/v1/inbox"
        assert request.url.params.get("owner_agent") == "agent://owner"
        return httpx.Response(200, json={"ok": True, "threads": [thread]})

    client = _client(handler)
    assert client.list_inbox(owner_agent="agent://owner") == {"ok": True, "threads": [thread]}


def test_get_inbox_thread_success() -> None:
    thread = _thread_payload()
    thread_id = str(thread["thread_id"])

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.method == "GET"
        assert request.url.path == f"/v1/inbox/{thread_id}"
        assert request.url.params.get("owner_agent") == "agent://owner"
        return httpx.Response(200, json={"ok": True, "thread": thread})

    client = _client(handler)
    assert client.get_inbox_thread(thread_id, owner_agent="agent://owner") == {"ok": True, "thread": thread}


def test_reply_inbox_thread_success() -> None:
    thread = _thread_payload()
    thread_id = str(thread["thread_id"])

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.method == "POST"
        assert request.url.path == f"/v1/inbox/{thread_id}/reply"
        assert request.url.params.get("owner_agent") == "agent://owner"
        assert request.headers["idempotency-key"] == "reply-1"
        assert request.read() == b'{"message":"ack"}'
        return httpx.Response(200, json={"ok": True, "thread": thread})

    client = _client(handler)
    assert client.reply_inbox_thread(
        thread_id,
        message="ack",
        owner_agent="agent://owner",
        idempotency_key="reply-1",
    ) == {"ok": True, "thread": thread}
