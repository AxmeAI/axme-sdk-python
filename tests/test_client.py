from __future__ import annotations

import json

import httpx
import pytest

from axme import AxmeClient, AxmeClientConfig
from axme.exceptions import AxmeAuthError, AxmeHttpError, AxmeRateLimitError, AxmeValidationError


def _transport(handler):
    return httpx.MockTransport(handler)


def _client(
    handler,
    api_key: str = "token",
    *,
    actor_token: str | None = None,
    bearer_token: str | None = None,
    max_retries: int = 2,
    retry_backoff_seconds: float = 0.0,
    auto_trace_id: bool = True,
) -> AxmeClient:
    cfg = AxmeClientConfig(
        base_url="https://api.axme.test",
        api_key=api_key,
        actor_token=actor_token,
        bearer_token=bearer_token,
        max_retries=max_retries,
        retry_backoff_seconds=retry_backoff_seconds,
        auto_trace_id=auto_trace_id,
    )
    default_headers = {
        "x-api-key": cfg.api_key,
        "Content-Type": "application/json",
    }
    if cfg.actor_token:
        default_headers["Authorization"] = f"Bearer {cfg.actor_token}"
    http_client = httpx.Client(
        transport=_transport(handler),
        base_url=cfg.base_url,
        headers=default_headers,
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


def _webhook_subscription_payload() -> dict[str, object]:
    return {
        "subscription_id": "44444444-4444-4444-8444-444444444444",
        "owner_agent": "agent://owner",
        "callback_url": "https://integrator.example/webhooks/axme",
        "event_types": ["inbox.thread_created"],
        "active": True,
        "description": "sdk-test",
        "created_at": "2026-02-28T00:00:00Z",
        "updated_at": "2026-02-28T00:00:01Z",
        "revoked_at": None,
        "secret_hint": "****hint",
    }


def test_health_success() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.method == "GET"
        assert request.url.path == "/health"
        assert request.headers["x-api-key"] == "token"
        return httpx.Response(200, json={"ok": True})

    client = _client(handler)
    assert client.health() == {"ok": True}


def test_health_propagates_trace_id_header() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.headers.get("x-trace-id") == "trace-123"
        return httpx.Response(200, json={"ok": True})

    client = _client(handler, auto_trace_id=False)
    assert client.health(trace_id="trace-123") == {"ok": True}


def test_health_includes_actor_token_authorization_when_configured() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.headers["x-api-key"] == "platform-key"
        assert request.headers["authorization"] == "Bearer actor-token"
        return httpx.Response(200, json={"ok": True})

    client = _client(handler, api_key="platform-key", actor_token="actor-token")
    assert client.health() == {"ok": True}


def test_client_config_rejects_conflicting_actor_token_aliases() -> None:
    with pytest.raises(ValueError, match="actor_token and bearer_token must match"):
        AxmeClientConfig(
            base_url="https://api.axme.test",
            api_key="platform-key",
            actor_token="token-a",
            bearer_token="token-b",
        )


def test_client_config_uses_default_base_url_when_not_provided() -> None:
    cfg = AxmeClientConfig(api_key="platform-key")
    assert cfg.base_url == "https://api.cloud.axme.ai"


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


def test_get_intent_success() -> None:
    intent_id = "22222222-2222-4222-8222-222222222222"

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.method == "GET"
        assert request.url.path == f"/v1/intents/{intent_id}"
        return httpx.Response(
            200,
            json={
                "ok": True,
                "intent": {
                    "intent_id": intent_id,
                    "status": "DELIVERED",
                    "created_at": "2026-02-28T00:00:00Z",
                    "intent_type": "notify.message.v1",
                    "correlation_id": "11111111-1111-1111-1111-111111111111",
                    "from_agent": "agent://from",
                    "to_agent": "agent://to",
                    "payload": {"text": "hello"},
                },
            },
        )

    client = _client(handler)
    assert client.get_intent(intent_id)["intent"]["intent_id"] == intent_id


def test_send_intent_returns_intent_id() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.method == "POST"
        assert request.url.path == "/v1/intents"
        body = json.loads(request.read().decode("utf-8"))
        assert isinstance(body["correlation_id"], str)
        return httpx.Response(200, json={"intent_id": "33333333-3333-4333-8333-333333333333"})

    client = _client(handler)
    intent_id = client.send_intent(
        {
            "intent_type": "notify.message.v1",
            "to_agent": "agent://x",
            "from_agent": "agent://y",
            "payload": {"text": "hello"},
        },
        idempotency_key="send-1",
    )
    assert intent_id == "33333333-3333-4333-8333-333333333333"


def test_send_intent_requires_response_intent_id() -> None:
    client = _client(lambda request: httpx.Response(200, json={"ok": True}))

    with pytest.raises(ValueError, match="intent_id"):
        client.send_intent(
            {
                "intent_type": "notify.message.v1",
                "to_agent": "agent://x",
                "from_agent": "agent://y",
                "payload": {},
            }
        )


def test_list_intent_events_success() -> None:
    intent_id = "22222222-2222-4222-8222-222222222222"

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.method == "GET"
        assert request.url.path == f"/v1/intents/{intent_id}/events"
        assert request.url.params.get("since") == "2"
        return httpx.Response(
            200,
            json={
                "ok": True,
                "events": [
                    {
                        "intent_id": intent_id,
                        "seq": 3,
                        "event_type": "intent.completed",
                        "status": "COMPLETED",
                        "at": "2026-02-28T00:00:10Z",
                    }
                ],
            },
        )

    client = _client(handler)
    response = client.list_intent_events(intent_id, since=2)
    assert response["ok"] is True
    assert response["events"][0]["seq"] == 3


def test_resolve_intent_success() -> None:
    intent_id = "22222222-2222-4222-8222-222222222222"

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.method == "POST"
        assert request.url.path == f"/v1/intents/{intent_id}/resolve"
        assert request.headers["idempotency-key"] == "resolve-1"
        body = json.loads(request.read().decode("utf-8"))
        assert body["status"] == "COMPLETED"
        return httpx.Response(
            200,
            json={
                "ok": True,
                "intent": {"intent_id": intent_id, "status": "COMPLETED"},
                "event": {"intent_id": intent_id, "seq": 3, "event_type": "intent.completed", "status": "COMPLETED"},
                "completion_delivery": {"delivered": False, "reason": "reply_to_not_set"},
            },
        )

    client = _client(handler)
    response = client.resolve_intent(
        intent_id,
        {"status": "COMPLETED", "result": {"answer": "done"}},
        idempotency_key="resolve-1",
    )
    assert response["event"]["event_type"] == "intent.completed"


def test_resolve_intent_supports_owner_scope_and_control_headers() -> None:
    intent_id = "22222222-2222-4222-8222-222222222222"

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.method == "POST"
        assert request.url.path == f"/v1/intents/{intent_id}/resolve"
        assert request.url.params.get("owner_agent") == "agent://owner"
        assert request.headers["x-owner-agent"] == "agent://owner"
        assert request.headers["authorization"] == "Bearer scoped-token"
        body = json.loads(request.read().decode("utf-8"))
        assert body["expected_policy_generation"] == 3
        return httpx.Response(
            200,
            json={"ok": True, "applied": False, "reason": "stale_policy_generation", "policy_generation": 4},
        )

    client = _client(handler, auto_trace_id=False)
    response = client.resolve_intent(
        intent_id,
        {"status": "COMPLETED", "expected_policy_generation": 3},
        owner_agent="agent://owner",
        x_owner_agent="agent://owner",
        authorization="Bearer scoped-token",
        trace_id="trace-abc",
    )
    assert response["ok"] is True
    assert response["applied"] is False


def test_resume_intent_success() -> None:
    intent_id = "22222222-2222-4222-8222-222222222222"

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.method == "POST"
        assert request.url.path == f"/v1/intents/{intent_id}/resume"
        assert request.url.params.get("owner_agent") == "agent://owner"
        assert request.headers["idempotency-key"] == "resume-1"
        body = json.loads(request.read().decode("utf-8"))
        assert body["approve_current_step"] is True
        return httpx.Response(200, json={"ok": True, "applied": True, "intent": {"intent_id": intent_id}})

    client = _client(handler)
    response = client.resume_intent(
        intent_id,
        {"approve_current_step": True, "expected_policy_generation": 2},
        owner_agent="agent://owner",
        idempotency_key="resume-1",
    )
    assert response["ok"] is True
    assert response["applied"] is True


def test_update_intent_controls_success() -> None:
    intent_id = "22222222-2222-4222-8222-222222222222"

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.method == "POST"
        assert request.url.path == f"/v1/intents/{intent_id}/controls"
        body = json.loads(request.read().decode("utf-8"))
        assert body["controls_patch"]["timeout_seconds"] == 120
        return httpx.Response(200, json={"ok": True, "applied": True, "policy_generation": 5})

    client = _client(handler)
    response = client.update_intent_controls(
        intent_id,
        {"controls_patch": {"timeout_seconds": 120}, "expected_policy_generation": 5},
    )
    assert response["ok"] is True
    assert response["applied"] is True
    assert response["policy_generation"] == 5


def test_update_intent_policy_success() -> None:
    intent_id = "22222222-2222-4222-8222-222222222222"

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.method == "POST"
        assert request.url.path == f"/v1/intents/{intent_id}/policy"
        assert request.url.params.get("owner_agent") == "agent://creator"
        body = json.loads(request.read().decode("utf-8"))
        assert body["grants_patch"]["delegate:agent://ops"]["allow"] == ["resume", "update_controls"]
        assert body["envelope_patch"]["max_retry_count"] == 10
        return httpx.Response(200, json={"ok": True, "applied": True, "policy_generation": 6})

    client = _client(handler)
    response = client.update_intent_policy(
        intent_id,
        {
            "grants_patch": {"delegate:agent://ops": {"allow": ["resume", "update_controls"]}},
            "envelope_patch": {"max_retry_count": 10},
            "expected_policy_generation": 5,
        },
        owner_agent="agent://creator",
    )
    assert response["ok"] is True
    assert response["applied"] is True
    assert response["policy_generation"] == 6


def test_observe_prefers_stream_and_yields_terminal_event() -> None:
    intent_id = "22222222-2222-4222-8222-222222222222"

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.method == "GET"
        assert request.url.path == f"/v1/intents/{intent_id}/events/stream"
        assert request.url.params.get("since") == "1"
        assert request.url.params.get("wait_seconds") == "5"
        sse_payload = (
            "id: 2\n"
            "event: intent.submitted\n"
            "data: {\"intent_id\":\"22222222-2222-4222-8222-222222222222\",\"seq\":2,"
            "\"event_type\":\"intent.submitted\",\"status\":\"SUBMITTED\",\"at\":\"2026-02-28T00:00:01Z\"}\n\n"
            "id: 3\n"
            "event: intent.completed\n"
            "data: {\"intent_id\":\"22222222-2222-4222-8222-222222222222\",\"seq\":3,"
            "\"event_type\":\"intent.completed\",\"status\":\"COMPLETED\",\"at\":\"2026-02-28T00:00:10Z\"}\n\n"
        )
        return httpx.Response(200, text=sse_payload)

    client = _client(handler)
    observed = list(client.observe(intent_id, since=1, wait_seconds=5, poll_interval_seconds=0))
    assert [item["event_type"] for item in observed] == ["intent.submitted", "intent.completed"]


def test_observe_falls_back_to_polling_when_stream_unavailable() -> None:
    intent_id = "22222222-2222-4222-8222-222222222222"
    calls = {"stream": 0, "poll": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/events/stream"):
            calls["stream"] += 1
            return httpx.Response(404, json={"error": "not found"})
        assert request.url.path.endswith("/events")
        calls["poll"] += 1
        return httpx.Response(
            200,
            json={
                "ok": True,
                "events": [
                    {
                        "intent_id": intent_id,
                        "seq": 1,
                        "event_type": "intent.created",
                        "status": "CREATED",
                        "at": "2026-02-28T00:00:00Z",
                    },
                    {
                        "intent_id": intent_id,
                        "seq": 2,
                        "event_type": "intent.completed",
                        "status": "COMPLETED",
                        "at": "2026-02-28T00:00:10Z",
                    },
                ],
            },
        )

    client = _client(handler)
    observed = list(client.observe(intent_id, poll_interval_seconds=0))
    assert [item["event_type"] for item in observed] == ["intent.created", "intent.completed"]
    assert calls["stream"] == 1
    assert calls["poll"] == 1


def test_wait_for_raises_timeout_without_terminal_event() -> None:
    intent_id = "22222222-2222-4222-8222-222222222222"

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/events/stream"):
            return httpx.Response(404, json={"error": "not found"})
        return httpx.Response(200, json={"ok": True, "events": []})

    client = _client(handler)
    with pytest.raises(TimeoutError):
        client.wait_for(intent_id, timeout_seconds=0.01, poll_interval_seconds=0)


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
        assert json.loads(request.read().decode("utf-8")) == {"message": "ack"}
        return httpx.Response(200, json={"ok": True, "thread": thread})

    client = _client(handler)
    assert client.reply_inbox_thread(
        thread_id,
        message="ack",
        owner_agent="agent://owner",
        idempotency_key="reply-1",
    ) == {"ok": True, "thread": thread}


def test_list_inbox_changes_sends_pagination_params() -> None:
    thread = _thread_payload()

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.method == "GET"
        assert request.url.path == "/v1/inbox/changes"
        assert request.url.params.get("owner_agent") == "agent://owner"
        assert request.url.params.get("cursor") == "cur-1"
        assert request.url.params.get("limit") == "50"
        return httpx.Response(
            200,
            json={
                "ok": True,
                "changes": [{"cursor": "cur-2", "thread": thread}],
                "next_cursor": "cur-2",
                "has_more": True,
            },
        )

    client = _client(handler)
    assert client.list_inbox_changes(owner_agent="agent://owner", cursor="cur-1", limit=50) == {
        "ok": True,
        "changes": [{"cursor": "cur-2", "thread": thread}],
        "next_cursor": "cur-2",
        "has_more": True,
    }


def test_delegate_inbox_thread_success() -> None:
    thread = _thread_payload()
    thread_id = str(thread["thread_id"])
    payload = {"delegate_to": "agent://example/delegate", "note": "handoff"}

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.method == "POST"
        assert request.url.path == f"/v1/inbox/{thread_id}/delegate"
        assert request.url.params.get("owner_agent") == "agent://owner"
        assert request.headers["idempotency-key"] == "delegate-1"
        assert json.loads(request.read().decode("utf-8")) == payload
        return httpx.Response(200, json={"ok": True, "thread": thread})

    client = _client(handler)
    assert client.delegate_inbox_thread(
        thread_id,
        payload,
        owner_agent="agent://owner",
        idempotency_key="delegate-1",
    ) == {"ok": True, "thread": thread}


def test_approve_inbox_thread_success() -> None:
    thread = _thread_payload()
    thread_id = str(thread["thread_id"])
    payload = {"comment": "approved"}

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.method == "POST"
        assert request.url.path == f"/v1/inbox/{thread_id}/approve"
        assert request.url.params.get("owner_agent") == "agent://owner"
        assert request.headers["idempotency-key"] == "approve-1"
        assert json.loads(request.read().decode("utf-8")) == payload
        return httpx.Response(200, json={"ok": True, "thread": thread})

    client = _client(handler)
    assert client.approve_inbox_thread(
        thread_id,
        payload,
        owner_agent="agent://owner",
        idempotency_key="approve-1",
    ) == {"ok": True, "thread": thread}


def test_reject_inbox_thread_success() -> None:
    thread = _thread_payload()
    thread_id = str(thread["thread_id"])
    payload = {"comment": "rejected"}

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.method == "POST"
        assert request.url.path == f"/v1/inbox/{thread_id}/reject"
        assert request.url.params.get("owner_agent") == "agent://owner"
        assert request.headers["idempotency-key"] == "reject-1"
        assert json.loads(request.read().decode("utf-8")) == payload
        return httpx.Response(200, json={"ok": True, "thread": thread})

    client = _client(handler)
    assert client.reject_inbox_thread(
        thread_id,
        payload,
        owner_agent="agent://owner",
        idempotency_key="reject-1",
    ) == {"ok": True, "thread": thread}


def test_delete_inbox_messages_success() -> None:
    thread = _thread_payload()
    thread_id = str(thread["thread_id"])
    payload = {"mode": "self", "limit": 1}

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.method == "POST"
        assert request.url.path == f"/v1/inbox/{thread_id}/messages/delete"
        assert request.url.params.get("owner_agent") == "agent://owner"
        assert request.headers["idempotency-key"] == "delete-1"
        assert json.loads(request.read().decode("utf-8")) == payload
        return httpx.Response(
            200,
            json={
                "ok": True,
                "thread": thread,
                "mode": "self",
                "deleted_count": 1,
                "message_ids": ["msg-1"],
            },
        )

    client = _client(handler)
    assert client.delete_inbox_messages(
        thread_id,
        payload,
        owner_agent="agent://owner",
        idempotency_key="delete-1",
    )["deleted_count"] == 1


def test_decide_approval_success() -> None:
    approval_id = "55555555-5555-4555-8555-555555555555"

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.method == "POST"
        assert request.url.path == f"/v1/approvals/{approval_id}/decision"
        assert request.headers["idempotency-key"] == "approval-1"
        assert json.loads(request.read().decode("utf-8")) == {
            "decision": "approve",
            "comment": "approved",
        }
        return httpx.Response(
            200,
            json={
                "ok": True,
                "approval": {
                    "approval_id": approval_id,
                    "decision": "approve",
                    "comment": "approved",
                    "decided_at": "2026-02-28T00:00:01Z",
                },
            },
        )

    client = _client(handler)
    assert client.decide_approval(
        approval_id,
        decision="approve",
        comment="approved",
        idempotency_key="approval-1",
    )["approval"]["approval_id"] == approval_id


def test_get_capabilities_success() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.method == "GET"
        assert request.url.path == "/v1/capabilities"
        return httpx.Response(
            200,
            json={
                "ok": True,
                "capabilities": ["inbox", "intents"],
                "supported_intent_types": ["intent.ask.v1", "intent.notify.v1"],
            },
        )

    client = _client(handler)
    assert client.get_capabilities()["ok"] is True


def test_create_invite_success() -> None:
    token = "invite-token-0001"
    payload = {"owner_agent": "agent://owner", "recipient_hint": "receiver", "ttl_seconds": 3600}

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.method == "POST"
        assert request.url.path == "/v1/invites/create"
        assert request.headers["idempotency-key"] == "invite-create-1"
        body = json.loads(request.read().decode("utf-8"))
        assert body == payload
        return httpx.Response(
            200,
            json={
                "ok": True,
                "token": token,
                "invite_url": f"https://invite.example/{token}",
                "owner_agent": "agent://owner",
                "recipient_hint": "receiver",
                "status": "pending",
                "created_at": "2026-02-28T00:00:00Z",
                "expires_at": "2026-03-01T00:00:00Z",
            },
        )

    client = _client(handler)
    assert client.create_invite(payload, idempotency_key="invite-create-1")["token"] == token


def test_get_invite_success() -> None:
    token = "invite-token-0002"

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.method == "GET"
        assert request.url.path == f"/v1/invites/{token}"
        return httpx.Response(
            200,
            json={
                "ok": True,
                "token": token,
                "owner_agent": "agent://owner",
                "recipient_hint": "receiver",
                "status": "pending",
                "created_at": "2026-02-28T00:00:00Z",
                "expires_at": "2026-03-01T00:00:00Z",
                "accepted_at": None,
                "accepted_owner_agent": None,
                "nick": None,
                "public_address": None,
            },
        )

    client = _client(handler)
    assert client.get_invite(token)["status"] == "pending"


def test_accept_invite_success() -> None:
    token = "invite-token-0003"
    payload = {"nick": "@Invite.User", "display_name": "Invite User"}

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.method == "POST"
        assert request.url.path == f"/v1/invites/{token}/accept"
        assert request.headers["idempotency-key"] == "invite-accept-1"
        body = json.loads(request.read().decode("utf-8"))
        assert body == payload
        return httpx.Response(
            200,
            json={
                "ok": True,
                "token": token,
                "status": "accepted",
                "invite_owner_agent": "agent://owner",
                "user_id": "66666666-6666-4666-8666-666666666666",
                "owner_agent": "agent://accepted",
                "nick": "@Invite.User",
                "public_address": "invite.user@ax",
                "display_name": "Invite User",
                "accepted_at": "2026-02-28T00:00:10Z",
                "registry_bind_status": "propagated",
            },
        )

    client = _client(handler)
    assert client.accept_invite(token, payload, idempotency_key="invite-accept-1")["status"] == "accepted"


def test_create_media_upload_success() -> None:
    upload_id = "77777777-7777-4777-8777-777777777777"
    payload = {
        "owner_agent": "agent://owner",
        "filename": "contract.pdf",
        "mime_type": "application/pdf",
        "size_bytes": 12345,
    }

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.method == "POST"
        assert request.url.path == "/v1/media/create-upload"
        assert request.headers["idempotency-key"] == "media-create-1"
        body = json.loads(request.read().decode("utf-8"))
        assert body == payload
        return httpx.Response(
            200,
            json={
                "ok": True,
                "upload_id": upload_id,
                "owner_agent": "agent://owner",
                "bucket": "axme-media",
                "object_path": "agent-owner/contract.pdf",
                "upload_url": "https://upload.example/media/1",
                "status": "pending",
                "expires_at": "2026-03-01T00:00:00Z",
                "max_size_bytes": 10485760,
            },
        )

    client = _client(handler)
    assert client.create_media_upload(payload, idempotency_key="media-create-1")["upload_id"] == upload_id


def test_get_media_upload_success() -> None:
    upload_id = "77777777-7777-4777-8777-777777777777"

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.method == "GET"
        assert request.url.path == f"/v1/media/{upload_id}"
        return httpx.Response(
            200,
            json={
                "ok": True,
                "upload": {
                    "upload_id": upload_id,
                    "owner_agent": "agent://owner",
                    "bucket": "axme-media",
                    "object_path": "agent-owner/contract.pdf",
                    "mime_type": "application/pdf",
                    "filename": "contract.pdf",
                    "size_bytes": 12345,
                    "sha256": None,
                    "status": "pending",
                    "created_at": "2026-02-28T00:00:00Z",
                    "expires_at": "2026-03-01T00:00:00Z",
                    "finalized_at": None,
                    "download_url": None,
                    "preview_url": None,
                },
            },
        )

    client = _client(handler)
    assert client.get_media_upload(upload_id)["upload"]["status"] == "pending"


def test_finalize_media_upload_success() -> None:
    upload_id = "77777777-7777-4777-8777-777777777777"
    payload = {"upload_id": upload_id, "size_bytes": 12345}

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.method == "POST"
        assert request.url.path == "/v1/media/finalize-upload"
        assert request.headers["idempotency-key"] == "media-finalize-1"
        body = json.loads(request.read().decode("utf-8"))
        assert body == payload
        return httpx.Response(
            200,
            json={
                "ok": True,
                "upload_id": upload_id,
                "owner_agent": "agent://owner",
                "bucket": "axme-media",
                "object_path": "agent-owner/contract.pdf",
                "mime_type": "application/pdf",
                "size_bytes": 12345,
                "sha256": None,
                "status": "ready",
                "finalized_at": "2026-02-28T00:00:10Z",
            },
        )

    client = _client(handler)
    assert client.finalize_media_upload(payload, idempotency_key="media-finalize-1")["status"] == "ready"


def test_upsert_schema_success() -> None:
    semantic_type = "axme.calendar.schedule.v1"
    payload = {
        "semantic_type": semantic_type,
        "schema_json": {"type": "object", "required": ["date"], "properties": {"date": {"type": "string"}}},
        "compatibility_mode": "strict",
    }

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.method == "POST"
        assert request.url.path == "/v1/schemas"
        assert request.headers["idempotency-key"] == "schema-upsert-1"
        body = json.loads(request.read().decode("utf-8"))
        assert body == payload
        return httpx.Response(
            200,
            json={
                "ok": True,
                "schema": {
                    "semantic_type": semantic_type,
                    "schema_ref": f"schema://{semantic_type}",
                    "schema_hash": "a" * 64,
                    "compatibility_mode": "strict",
                    "scope": "tenant",
                    "owner_agent": "agent://owner",
                    "active": True,
                    "created_at": "2026-02-28T00:00:00Z",
                    "updated_at": "2026-02-28T00:00:01Z",
                },
            },
        )

    client = _client(handler)
    assert client.upsert_schema(payload, idempotency_key="schema-upsert-1")["schema"]["semantic_type"] == semantic_type


def test_get_schema_success() -> None:
    semantic_type = "axme.calendar.schedule.v1"

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.method == "GET"
        assert request.url.path == f"/v1/schemas/{semantic_type}"
        return httpx.Response(
            200,
            json={
                "ok": True,
                "schema": {
                    "semantic_type": semantic_type,
                    "schema_ref": f"schema://{semantic_type}",
                    "schema_hash": "b" * 64,
                    "compatibility_mode": "strict",
                    "scope": "tenant",
                    "owner_agent": "agent://owner",
                    "active": True,
                    "schema_json": {"type": "object", "properties": {"date": {"type": "string"}}},
                    "created_at": "2026-02-28T00:00:00Z",
                    "updated_at": "2026-02-28T00:00:01Z",
                },
            },
        )

    client = _client(handler)
    assert client.get_schema(semantic_type)["schema"]["semantic_type"] == semantic_type


def test_register_nick_success() -> None:
    payload = {"nick": "@partner.user", "display_name": "Partner User"}
    user_id = "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa"
    owner_agent = f"agent://user/{user_id}"

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.method == "POST"
        assert request.url.path == "/v1/users/register-nick"
        assert request.headers["idempotency-key"] == "nick-register-1"
        assert json.loads(request.read().decode("utf-8")) == payload
        return httpx.Response(
            200,
            json={
                "ok": True,
                "user_id": user_id,
                "owner_agent": owner_agent,
                "nick": "@partner.user",
                "public_address": "partner.user@ax",
                "display_name": "Partner User",
                "phone": None,
                "email": None,
                "created_at": "2026-02-28T00:00:00Z",
            },
        )

    client = _client(handler)
    assert client.register_nick(payload, idempotency_key="nick-register-1")["owner_agent"] == owner_agent


def test_check_nick_success() -> None:
    nick = "@partner.user"

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.method == "GET"
        assert request.url.path == "/v1/users/check-nick"
        assert request.url.params.get("nick") == nick
        return httpx.Response(
            200,
            json={
                "ok": True,
                "nick": nick,
                "normalized_nick": "partner.user",
                "public_address": "partner.user@ax",
                "available": True,
            },
        )

    client = _client(handler)
    assert client.check_nick(nick)["available"] is True


def test_rename_nick_success() -> None:
    payload = {"owner_agent": "agent://user/aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa", "nick": "@partner.new"}

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.method == "POST"
        assert request.url.path == "/v1/users/rename-nick"
        assert request.headers["idempotency-key"] == "nick-rename-1"
        assert json.loads(request.read().decode("utf-8")) == payload
        return httpx.Response(
            200,
            json={
                "ok": True,
                "user_id": "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa",
                "owner_agent": payload["owner_agent"],
                "nick": "@partner.new",
                "public_address": "partner.new@ax",
                "display_name": "Partner User",
                "phone": None,
                "email": None,
                "renamed_at": "2026-02-28T00:00:01Z",
            },
        )

    client = _client(handler)
    assert client.rename_nick(payload, idempotency_key="nick-rename-1")["nick"] == "@partner.new"


def test_get_user_profile_success() -> None:
    owner_agent = "agent://user/aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa"

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.method == "GET"
        assert request.url.path == "/v1/users/profile"
        assert request.url.params.get("owner_agent") == owner_agent
        return httpx.Response(
            200,
            json={
                "ok": True,
                "user_id": "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa",
                "owner_agent": owner_agent,
                "nick": "@partner.new",
                "normalized_nick": "partner.new",
                "public_address": "partner.new@ax",
                "display_name": "Partner User",
                "phone": None,
                "email": None,
                "updated_at": "2026-02-28T00:00:02Z",
            },
        )

    client = _client(handler)
    assert client.get_user_profile(owner_agent)["nick"] == "@partner.new"


def test_update_user_profile_success() -> None:
    payload = {
        "owner_agent": "agent://user/aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa",
        "display_name": "Partner Updated",
    }

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.method == "POST"
        assert request.url.path == "/v1/users/profile/update"
        assert request.headers["idempotency-key"] == "profile-update-1"
        assert json.loads(request.read().decode("utf-8")) == payload
        return httpx.Response(
            200,
            json={
                "ok": True,
                "user_id": "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa",
                "owner_agent": payload["owner_agent"],
                "nick": "@partner.new",
                "normalized_nick": "partner.new",
                "public_address": "partner.new@ax",
                "display_name": "Partner Updated",
                "phone": None,
                "email": None,
                "updated_at": "2026-02-28T00:00:03Z",
            },
        )

    client = _client(handler)
    assert client.update_user_profile(payload, idempotency_key="profile-update-1")["display_name"] == "Partner Updated"


@pytest.mark.parametrize(
    ("status_code", "expected_exception"),
    [
        (401, AxmeAuthError),
        (422, AxmeValidationError),
    ],
)
def test_client_maps_http_errors_to_typed_exceptions(status_code: int, expected_exception: type[Exception]) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(status_code, json={"message": "boom"})

    client = _client(handler)
    with pytest.raises(expected_exception):
        client.health()


def test_client_maps_rate_limit_error_with_retry_after() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(429, json={"message": "too many"}, headers={"Retry-After": "30"})

    client = _client(handler, max_retries=0)
    with pytest.raises(AxmeRateLimitError) as exc_info:
        client.list_inbox()
    assert exc_info.value.retry_after == 30
    assert isinstance(exc_info.value.body, dict)
    assert exc_info.value.body["message"] == "too many"


def test_create_and_list_service_accounts_success() -> None:
    org_id = "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa"
    workspace_id = "bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb"
    service_account_id = "sa_123"

    def handler(request: httpx.Request) -> httpx.Response:
        if request.method == "POST":
            assert request.url.path == "/v1/service-accounts"
            body = json.loads(request.read().decode("utf-8"))
            assert body["org_id"] == org_id
            assert body["workspace_id"] == workspace_id
            return httpx.Response(
                200,
                json={
                    "ok": True,
                    "service_account": {
                        "service_account_id": service_account_id,
                        "org_id": org_id,
                        "workspace_id": workspace_id,
                    },
                },
            )
        assert request.method == "GET"
        assert request.url.path == "/v1/service-accounts"
        assert request.url.params.get("org_id") == org_id
        assert request.url.params.get("workspace_id") == workspace_id
        return httpx.Response(200, json={"ok": True, "service_accounts": [{"service_account_id": service_account_id}]})

    client = _client(handler)
    created = client.create_service_account(
        {
            "org_id": org_id,
            "workspace_id": workspace_id,
            "name": "sdk-runner",
            "created_by_actor_id": "actor_sdk",
        }
    )
    assert created["service_account"]["service_account_id"] == service_account_id
    listed = client.list_service_accounts(org_id=org_id, workspace_id=workspace_id)
    assert listed["service_accounts"][0]["service_account_id"] == service_account_id


def test_get_service_account_success() -> None:
    service_account_id = "sa_abc"

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.method == "GET"
        assert request.url.path == f"/v1/service-accounts/{service_account_id}"
        return httpx.Response(200, json={"ok": True, "service_account": {"service_account_id": service_account_id}})

    client = _client(handler)
    fetched = client.get_service_account(service_account_id)
    assert fetched["service_account"]["service_account_id"] == service_account_id


def test_create_and_revoke_service_account_key_success() -> None:
    service_account_id = "sa_abc"
    key_id = "sak_abc"

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/keys"):
            assert request.method == "POST"
            assert request.url.path == f"/v1/service-accounts/{service_account_id}/keys"
            return httpx.Response(
                200,
                json={
                    "ok": True,
                    "key": {
                        "key_id": key_id,
                        "service_account_id": service_account_id,
                        "status": "active",
                        "token": "axme_sa_token",
                    },
                },
            )
        assert request.method == "POST"
        assert request.url.path == f"/v1/service-accounts/{service_account_id}/keys/{key_id}/revoke"
        return httpx.Response(200, json={"ok": True, "key": {"key_id": key_id, "status": "revoked"}})

    client = _client(handler)
    created = client.create_service_account_key(service_account_id, {"created_by_actor_id": "actor_sdk"})
    assert created["key"]["key_id"] == key_id
    revoked = client.revoke_service_account_key(service_account_id, key_id)
    assert revoked["key"]["status"] == "revoked"


def test_enterprise_track_f_family_methods_success() -> None:
    org_id = "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa"
    workspace_id = "bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb"
    member_id = "mem_123"
    access_request_id = "ar_123"
    principal_id = "prn_123"
    alias_id = "als_123"
    route_id = "rte_123"
    binding_id = "bnd_123"
    delivery_id = "dlv_123"
    invoice_id = "inv_123"
    calls: list[tuple[str, str]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        method_path = (request.method, request.url.path)
        calls.append(method_path)
        if method_path == ("POST", "/v1/organizations"):
            return httpx.Response(200, json={"ok": True, "organization": {"org_id": org_id}})
        if method_path == ("GET", f"/v1/organizations/{org_id}"):
            return httpx.Response(200, json={"ok": True, "organization": {"org_id": org_id}})
        if method_path == ("PATCH", f"/v1/organizations/{org_id}"):
            return httpx.Response(200, json={"ok": True, "organization": {"org_id": org_id}})
        if method_path == ("POST", f"/v1/organizations/{org_id}/workspaces"):
            return httpx.Response(200, json={"ok": True, "workspace": {"workspace_id": workspace_id}})
        if method_path == ("GET", f"/v1/organizations/{org_id}/workspaces"):
            return httpx.Response(200, json={"ok": True, "workspaces": [{"workspace_id": workspace_id}]})
        if method_path == ("PATCH", f"/v1/organizations/{org_id}/workspaces/{workspace_id}"):
            return httpx.Response(200, json={"ok": True, "workspace": {"workspace_id": workspace_id}})
        if method_path == ("GET", f"/v1/organizations/{org_id}/members"):
            return httpx.Response(200, json={"ok": True, "members": [{"member_id": member_id}]})
        if method_path == ("POST", f"/v1/organizations/{org_id}/members"):
            return httpx.Response(200, json={"ok": True, "member": {"member_id": member_id}})
        if method_path == ("PATCH", f"/v1/organizations/{org_id}/members/{member_id}"):
            return httpx.Response(200, json={"ok": True, "member": {"member_id": member_id}})
        if method_path == ("DELETE", f"/v1/organizations/{org_id}/members/{member_id}"):
            return httpx.Response(200, json={"ok": True, "result": {"member_id": member_id}})
        if method_path == ("POST", "/v1/access-requests"):
            return httpx.Response(200, json={"ok": True, "access_request": {"access_request_id": access_request_id}})
        if method_path == ("GET", "/v1/access-requests"):
            return httpx.Response(200, json={"ok": True, "access_requests": [{"access_request_id": access_request_id}]})
        if method_path == ("GET", f"/v1/access-requests/{access_request_id}"):
            return httpx.Response(200, json={"ok": True, "access_request": {"access_request_id": access_request_id}})
        if method_path == ("POST", f"/v1/access-requests/{access_request_id}/review"):
            return httpx.Response(200, json={"ok": True, "access_request": {"access_request_id": access_request_id}})
        if method_path == ("PATCH", "/v1/quotas"):
            return httpx.Response(200, json={"ok": True, "quota_policy": {"org_id": org_id}})
        if method_path == ("GET", "/v1/quotas"):
            return httpx.Response(200, json={"ok": True, "quota_policy": {"org_id": org_id}})
        if method_path == ("GET", "/v1/usage/summary"):
            return httpx.Response(200, json={"ok": True, "summary": {"org_id": org_id}})
        if method_path == ("GET", "/v1/usage/timeseries"):
            return httpx.Response(200, json={"ok": True, "series": {"org_id": org_id}})
        if method_path == ("POST", "/v1/principals"):
            return httpx.Response(200, json={"ok": True, "principal": {"principal_id": principal_id}})
        if method_path == ("GET", f"/v1/principals/{principal_id}"):
            return httpx.Response(200, json={"ok": True, "principal": {"principal_id": principal_id}})
        if method_path == ("POST", "/v1/aliases"):
            return httpx.Response(200, json={"ok": True, "alias": {"alias_id": alias_id}})
        if method_path == ("GET", "/v1/aliases"):
            return httpx.Response(200, json={"ok": True, "aliases": [{"alias_id": alias_id}]})
        if method_path == ("GET", "/v1/aliases/resolve"):
            return httpx.Response(200, json={"ok": True, "resolution": {"principal": {"principal_id": principal_id}}})
        if method_path == ("POST", f"/v1/aliases/{alias_id}/revoke"):
            return httpx.Response(200, json={"ok": True, "alias": {"alias_id": alias_id, "status": "revoked"}})
        if method_path == ("POST", "/v1/routing/endpoints"):
            return httpx.Response(200, json={"ok": True, "route": {"route_id": route_id}})
        if method_path == ("GET", "/v1/routing/endpoints"):
            return httpx.Response(200, json={"ok": True, "routes": [{"route_id": route_id}]})
        if method_path == ("PATCH", f"/v1/routing/endpoints/{route_id}"):
            return httpx.Response(200, json={"ok": True, "route": {"route_id": route_id}})
        if method_path == ("DELETE", f"/v1/routing/endpoints/{route_id}"):
            return httpx.Response(200, json={"ok": True, "result": {"route_id": route_id}})
        if method_path == ("POST", "/v1/routing/resolve"):
            return httpx.Response(200, json={"ok": True, "resolution": {"selected_route": {"route_id": route_id}}})
        if method_path == ("POST", "/v1/transports/bindings"):
            return httpx.Response(200, json={"ok": True, "binding": {"binding_id": binding_id}})
        if method_path == ("GET", "/v1/transports/bindings"):
            return httpx.Response(200, json={"ok": True, "bindings": [{"binding_id": binding_id}]})
        if method_path == ("DELETE", f"/v1/transports/bindings/{binding_id}"):
            return httpx.Response(200, json={"ok": True, "result": {"binding_id": binding_id}})
        if method_path == ("POST", "/v1/deliveries"):
            return httpx.Response(200, json={"ok": True, "delivery": {"delivery_id": delivery_id}})
        if method_path == ("GET", "/v1/deliveries"):
            return httpx.Response(200, json={"ok": True, "deliveries": [{"delivery_id": delivery_id}]})
        if method_path == ("GET", f"/v1/deliveries/{delivery_id}"):
            return httpx.Response(200, json={"ok": True, "delivery": {"delivery_id": delivery_id}})
        if method_path == ("POST", f"/v1/deliveries/{delivery_id}/replay"):
            return httpx.Response(200, json={"ok": True, "delivery": {"delivery_id": "dlv_replay"}})
        if method_path == ("PATCH", "/v1/billing/plan"):
            return httpx.Response(200, json={"ok": True, "billing_plan": {"org_id": org_id}})
        if method_path == ("GET", "/v1/billing/plan"):
            return httpx.Response(200, json={"ok": True, "billing_plan": {"org_id": org_id}})
        if method_path == ("GET", "/v1/billing/invoices"):
            return httpx.Response(200, json={"ok": True, "invoices": [{"invoice_id": invoice_id}]})
        if method_path == ("GET", f"/v1/billing/invoices/{invoice_id}"):
            return httpx.Response(200, json={"ok": True, "invoice": {"invoice_id": invoice_id}})
        raise AssertionError(f"unexpected request: {method_path}")

    client = _client(handler)
    assert client.create_organization({"org_id": org_id, "name": "Acme"})["ok"] is True
    assert client.get_organization(org_id)["ok"] is True
    assert client.update_organization(org_id, {"name": "Acme Updated"})["ok"] is True
    assert client.create_workspace(org_id, {"workspace_id": workspace_id, "name": "Prod", "environment": "production"})["ok"] is True
    assert client.list_workspaces(org_id)["ok"] is True
    assert client.update_workspace(org_id, workspace_id, {"name": "Production"})["ok"] is True
    assert client.list_organization_members(org_id, workspace_id=workspace_id)["ok"] is True
    assert client.add_organization_member(org_id, {"actor_id": "actor_member", "role": "member", "workspace_id": workspace_id})["ok"] is True
    assert client.update_organization_member(org_id, member_id, {"status": "suspended"})["ok"] is True
    assert client.remove_organization_member(org_id, member_id)["ok"] is True
    assert client.create_access_request({"request_type": "workspace_join", "requester_actor_id": "actor_member"})["ok"] is True
    assert client.list_access_requests(org_id=org_id, workspace_id=workspace_id, state="pending")["ok"] is True
    assert client.get_access_request(access_request_id)["ok"] is True
    assert client.review_access_request(access_request_id, {"decision": "approve", "reviewer_actor_id": "actor_admin"})["ok"] is True
    assert client.update_quota({"org_id": org_id, "workspace_id": workspace_id, "dimensions": {}, "overage_mode": "block", "updated_by_actor_id": "actor_admin"})["ok"] is True
    assert client.get_quota(org_id=org_id, workspace_id=workspace_id)["ok"] is True
    assert client.get_usage_summary(org_id=org_id, workspace_id=workspace_id)["ok"] is True
    assert client.get_usage_timeseries(org_id=org_id, workspace_id=workspace_id)["ok"] is True
    assert client.create_principal({"org_id": org_id, "workspace_id": workspace_id, "principal_type": "service_agent"})["ok"] is True
    assert client.get_principal(principal_id)["ok"] is True
    assert client.bind_alias({"principal_id": principal_id, "alias": "agent://acme/billing", "alias_type": "service"})["ok"] is True
    assert client.list_aliases(org_id=org_id, workspace_id=workspace_id)["ok"] is True
    assert client.resolve_alias(org_id=org_id, workspace_id=workspace_id, alias="agent://acme/billing")["ok"] is True
    assert client.revoke_alias(alias_id)["ok"] is True
    assert client.register_routing_endpoint({"principal_id": principal_id, "transport_type": "http", "endpoint_url": "https://example", "auth_mode": "jwt"})["ok"] is True
    assert client.list_routing_endpoints(org_id=org_id, workspace_id=workspace_id)["ok"] is True
    assert client.update_routing_endpoint(route_id, {"priority": 1})["ok"] is True
    assert client.remove_routing_endpoint(route_id)["ok"] is True
    assert client.resolve_routing({"org_id": org_id, "workspace_id": workspace_id, "principal_id": principal_id})["ok"] is True
    assert client.upsert_transport_binding({"principal_id": principal_id, "transport_type": "http", "transport_handle": "https://example"})["ok"] is True
    assert client.list_transport_bindings(org_id=org_id, workspace_id=workspace_id)["ok"] is True
    assert client.remove_transport_binding(binding_id)["ok"] is True
    assert client.submit_delivery({"org_id": org_id, "workspace_id": workspace_id, "principal_id": principal_id, "payload": {"event": "test"}})["ok"] is True
    assert client.list_deliveries(org_id=org_id, workspace_id=workspace_id)["ok"] is True
    assert client.get_delivery(delivery_id)["ok"] is True
    assert client.replay_delivery(delivery_id)["ok"] is True
    assert client.update_billing_plan({"org_id": org_id, "workspace_id": workspace_id, "plan_code": "enterprise", "currency": "USD", "monthly_commit_minor": 100, "overage_unit_price_minor": 1, "updated_by_actor_id": "actor_admin"})["ok"] is True
    assert client.get_billing_plan(org_id=org_id, workspace_id=workspace_id)["ok"] is True
    assert client.list_billing_invoices(org_id=org_id, workspace_id=workspace_id)["ok"] is True
    assert client.get_billing_invoice(invoice_id)["ok"] is True
    assert len(calls) == 40


def test_upsert_webhook_subscription_success() -> None:
    subscription = _webhook_subscription_payload()
    request_payload = {
        "callback_url": "https://integrator.example/webhooks/axme",
        "event_types": ["inbox.thread_created"],
        "active": True,
    }

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.method == "POST"
        assert request.url.path == "/v1/webhooks/subscriptions"
        assert request.headers["idempotency-key"] == "wh-1"
        assert json.loads(request.read().decode("utf-8")) == request_payload
        return httpx.Response(200, json={"ok": True, "subscription": subscription})

    client = _client(handler)
    assert client.upsert_webhook_subscription(request_payload, idempotency_key="wh-1") == {
        "ok": True,
        "subscription": subscription,
    }


def test_list_webhook_subscriptions_success() -> None:
    subscription = _webhook_subscription_payload()

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.method == "GET"
        assert request.url.path == "/v1/webhooks/subscriptions"
        assert request.url.params.get("owner_agent") == "agent://owner"
        return httpx.Response(200, json={"ok": True, "subscriptions": [subscription]})

    client = _client(handler)
    assert client.list_webhook_subscriptions(owner_agent="agent://owner") == {
        "ok": True,
        "subscriptions": [subscription],
    }


def test_delete_webhook_subscription_success() -> None:
    subscription_id = "44444444-4444-4444-8444-444444444444"

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.method == "DELETE"
        assert request.url.path == f"/v1/webhooks/subscriptions/{subscription_id}"
        assert request.url.params.get("owner_agent") == "agent://owner"
        return httpx.Response(200, json={"ok": True, "subscription_id": subscription_id, "revoked_at": "2026-02-28T00:00:03Z"})

    client = _client(handler)
    assert client.delete_webhook_subscription(subscription_id, owner_agent="agent://owner") == {
        "ok": True,
        "subscription_id": subscription_id,
        "revoked_at": "2026-02-28T00:00:03Z",
    }


def test_publish_webhook_event_success() -> None:
    event_id = "33333333-3333-4333-8333-333333333333"
    request_payload = {"event_type": "inbox.thread_created", "source": "sdk-test", "payload": {"thread_id": "t-1"}}

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.method == "POST"
        assert request.url.path == "/v1/webhooks/events"
        assert request.url.params.get("owner_agent") == "agent://owner"
        return httpx.Response(
            200,
            json={
                "ok": True,
                "accepted_at": "2026-02-28T00:00:01Z",
                "event_type": "inbox.thread_created",
                "source": "sdk-test",
                "owner_agent": "agent://owner",
                "event_id": event_id,
                "queued_deliveries": 1,
                "processed_deliveries": 1,
                "delivered": 1,
                "pending": 0,
                "dead_lettered": 0,
            },
        )

    client = _client(handler)
    assert client.publish_webhook_event(request_payload, owner_agent="agent://owner")["event_id"] == event_id


def test_replay_webhook_event_success() -> None:
    event_id = "33333333-3333-4333-8333-333333333333"

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.method == "POST"
        assert request.url.path == f"/v1/webhooks/events/{event_id}/replay"
        assert request.url.params.get("owner_agent") == "agent://owner"
        return httpx.Response(
            200,
            json={
                "ok": True,
                "event_id": event_id,
                "owner_agent": "agent://owner",
                "event_type": "inbox.thread_created",
                "queued_deliveries": 1,
                "processed_deliveries": 1,
                "delivered": 1,
                "pending": 0,
                "dead_lettered": 0,
                "replayed_at": "2026-02-28T00:00:02Z",
            },
        )

    client = _client(handler)
    assert client.replay_webhook_event(event_id, owner_agent="agent://owner")["event_id"] == event_id


def test_retries_retryable_get_on_transient_server_error() -> None:
    attempts = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal attempts
        attempts += 1
        if attempts == 1:
            return httpx.Response(500, json={"error": "temporary"})
        return httpx.Response(200, json={"ok": True, "threads": []})

    client = _client(handler)
    assert client.list_inbox(owner_agent="agent://owner") == {"ok": True, "threads": []}
    assert attempts == 2


def test_retries_post_when_idempotency_key_is_present() -> None:
    attempts = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal attempts
        attempts += 1
        if attempts == 1:
            return httpx.Response(500, json={"error": "temporary"})
        return httpx.Response(200, json={"intent_id": "it_123"})

    client = _client(handler)
    assert (
        client.create_intent(
            {"intent_type": "notify.message.v1", "to_agent": "agent://x", "from_agent": "agent://y", "payload": {}},
            correlation_id="11111111-1111-1111-1111-111111111111",
            idempotency_key="idem-retry",
        )
        == {"intent_id": "it_123"}
    )
    assert attempts == 2


def test_does_not_retry_post_without_idempotency_key() -> None:
    attempts = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal attempts
        attempts += 1
        return httpx.Response(500, json={"error": "temporary"})

    client = _client(handler)
    with pytest.raises(AxmeHttpError):
        client.create_intent(
            {"intent_type": "notify.message.v1", "to_agent": "agent://x", "from_agent": "agent://y", "payload": {}},
            correlation_id="11111111-1111-1111-1111-111111111111",
        )
    assert attempts == 1


def test_mcp_initialize_success() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.method == "POST"
        assert request.url.path == "/mcp"
        body = json.loads(request.read().decode("utf-8"))
        assert body["jsonrpc"] == "2.0"
        assert body["method"] == "initialize"
        assert body["params"]["protocolVersion"] == "2024-11-05"
        return httpx.Response(
            200,
            json={
                "jsonrpc": "2.0",
                "id": body["id"],
                "result": {"protocolVersion": "2024-11-05", "capabilities": {"tools": {"listChanged": False}}},
            },
        )

    client = _client(handler)
    result = client.mcp_initialize()
    assert result["protocolVersion"] == "2024-11-05"


def test_mcp_list_tools_and_call_tool_with_schema_validation() -> None:
    calls: list[dict[str, object]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.read().decode("utf-8"))
        calls.append(body)
        if body["method"] == "tools/list":
            return httpx.Response(
                200,
                json={
                    "jsonrpc": "2.0",
                    "id": body["id"],
                    "result": {
                        "tools": [
                            {
                                "name": "axme.send",
                                "inputSchema": {
                                    "type": "object",
                                    "required": ["to"],
                                    "properties": {
                                        "to": {"type": "string"},
                                        "text": {"type": "string"},
                                        "idempotency_key": {"type": "string"},
                                        "owner_agent": {"type": "string"},
                                    },
                                },
                            }
                        ]
                    },
                },
            )
        assert body["method"] == "tools/call"
        assert body["params"]["name"] == "axme.send"
        assert body["params"]["owner_agent"] == "agent://owner/default"
        args = body["params"]["arguments"]
        assert args["owner_agent"] == "agent://owner/default"
        assert args["idempotency_key"] == "mcp-idem-1"
        return httpx.Response(
            200,
            json={
                "jsonrpc": "2.0",
                "id": body["id"],
                "result": {"ok": True, "tool": "axme.send", "status": "completed"},
            },
        )

    observed_events: list[dict[str, object]] = []
    cfg = AxmeClientConfig(
        base_url="https://api.axme.test",
        api_key="token",
        default_owner_agent="agent://owner/default",
        mcp_observer=lambda event: observed_events.append(event),
    )
    http_client = httpx.Client(
        transport=_transport(handler),
        base_url=cfg.base_url,
        headers={
            "x-api-key": cfg.api_key,
            "Content-Type": "application/json",
        },
    )
    client = AxmeClient(cfg, http_client=http_client)
    tools = client.mcp_list_tools()
    assert isinstance(tools["tools"], list)
    call_result = client.mcp_call_tool(
        "axme.send",
        arguments={"to": "agent://bob", "text": "hello"},
        idempotency_key="mcp-idem-1",
    )
    assert call_result["ok"] is True
    assert len(calls) == 2
    assert any(event.get("phase") == "request" for event in observed_events)
    assert any(event.get("phase") == "response" for event in observed_events)


def test_mcp_call_tool_validates_required_arguments() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.read().decode("utf-8"))
        if body["method"] == "tools/list":
            return httpx.Response(
                200,
                json={
                    "jsonrpc": "2.0",
                    "id": body["id"],
                    "result": {
                        "tools": [
                            {
                                "name": "axme.reply",
                                "inputSchema": {
                                    "type": "object",
                                    "required": ["thread_id", "message"],
                                    "properties": {
                                        "thread_id": {"type": "string"},
                                        "message": {"type": "string"},
                                    },
                                },
                            }
                        ]
                    },
                },
            )
        return httpx.Response(500, json={"error": "unexpected"})

    client = _client(handler)
    client.mcp_list_tools()
    with pytest.raises(ValueError, match="missing required MCP tool arguments"):
        client.mcp_call_tool("axme.reply", arguments={"thread_id": "t-1"})


def test_mcp_call_tool_maps_rpc_errors() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.read().decode("utf-8"))
        return httpx.Response(
            200,
            json={
                "jsonrpc": "2.0",
                "id": body.get("id"),
                "error": {"code": -32602, "message": "invalid params"},
            },
        )

    client = _client(handler)
    with pytest.raises(AxmeValidationError) as exc_info:
        client.mcp_call_tool("axme.send", arguments={"to": "agent://bob"})
    assert exc_info.value.status_code == 422


def test_mcp_call_tool_retries_http_failure_when_retryable() -> None:
    attempts = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal attempts
        attempts += 1
        if attempts == 1:
            return httpx.Response(500, json={"error": "temporary"})
        body = json.loads(request.read().decode("utf-8"))
        return httpx.Response(
            200,
            json={
                "jsonrpc": "2.0",
                "id": body.get("id"),
                "result": {"ok": True, "tool": "axme.send", "status": "completed"},
            },
        )

    client = _client(handler)
    result = client.mcp_call_tool(
        "axme.send",
        arguments={"to": "agent://bob", "text": "hello"},
        idempotency_key="idem-1",
    )
    assert result["ok"] is True
    assert attempts == 2


# ---------------------------------------------------------------------------
# listen(address) — agent intent stream
# ---------------------------------------------------------------------------


def _sse(events: list[tuple[str, dict]]) -> str:
    """Build a minimal SSE payload from (event_type, payload) pairs."""
    parts = []
    for event_type, payload in events:
        parts.append(f"event: {event_type}\ndata: {json.dumps(payload)}\n\n")
    return "".join(parts)


def test_listen_yields_intent_events_from_sse() -> None:
    address = "agent://acme/main/router"
    intent1 = {
        "intent_id": "aaaa-1",
        "seq": 1,
        "event_type": "intent.submitted",
        "status": "SUBMITTED",
        "at": "2026-03-01T00:00:00Z",
    }
    intent2 = {
        "intent_id": "bbbb-2",
        "seq": 2,
        "event_type": "intent.submitted",
        "status": "SUBMITTED",
        "at": "2026-03-01T00:00:01Z",
    }

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.method == "GET"
        assert request.url.path == "/v1/agents/acme/main/router/intents/stream"
        # Deliver two intents then keepalive to end the stream segment
        return httpx.Response(
            200,
            text=_sse([("intent.submitted", intent1), ("intent.submitted", intent2)])
            + "event: stream.timeout\ndata: {}\n\n",
        )

    client = _client(handler)
    gen = client.listen(address)
    received = [next(gen), next(gen)]
    assert received[0]["intent_id"] == "aaaa-1"
    assert received[1]["intent_id"] == "bbbb-2"


def test_listen_strips_agent_scheme_from_url() -> None:
    """address with and without 'agent://' prefix must hit the same URL path."""
    paths_seen: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        paths_seen.append(request.url.path)
        # Return one intent then stream.timeout to end the stream cleanly
        intent = {"intent_id": "x1", "seq": 1, "event_type": "intent.submitted", "status": "SUBMITTED", "at": "2026-03-01T00:00:00Z"}
        return httpx.Response(200, text=_sse([("intent.submitted", intent)]) + "event: stream.timeout\ndata: {}\n\n")

    client = _client(handler)
    # with scheme — consume one event
    next(client.listen("agent://org/ws/bot"))
    # without scheme — consume one event
    next(client.listen("org/ws/bot"))
    assert paths_seen[0] == paths_seen[1] == "/v1/agents/org/ws/bot/intents/stream"


def test_listen_since_cursor_forwarded() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.params.get("since") == "42"
        intent = {"intent_id": "x1", "seq": 43, "event_type": "intent.submitted", "status": "SUBMITTED", "at": "2026-03-01T00:00:00Z"}
        return httpx.Response(200, text=_sse([("intent.submitted", intent)]) + "event: stream.timeout\ndata: {}\n\n")

    client = _client(handler)
    result = next(client.listen("org/ws/bot", since=42))
    assert result["intent_id"] == "x1"


def test_listen_reconnects_on_stream_timeout_keepalive() -> None:
    """A stream.timeout SSE event causes the client to reconnect."""
    calls: list[int] = []
    intent = {
        "intent_id": "cc-3",
        "seq": 5,
        "event_type": "intent.submitted",
        "status": "SUBMITTED",
        "at": "2026-03-01T00:00:00Z",
    }

    def handler(request: httpx.Request) -> httpx.Response:
        call_no = len(calls) + 1
        calls.append(call_no)
        if call_no == 1:
            # first response: keepalive only → reconnect
            return httpx.Response(
                200,
                text="event: stream.timeout\ndata: {}\n\n",
            )
        # second response: real intent + keepalive → stops reconnect
        return httpx.Response(
            200,
            text=_sse([("intent.submitted", intent)]) + "event: stream.timeout\ndata: {}\n\n",
        )

    client = _client(handler)
    # consume one event (which only arrives on the second request)
    received = next(client.listen("org/ws/bot", wait_seconds=1))
    assert received["intent_id"] == "cc-3"
    assert len(calls) >= 2


def test_listen_advances_since_cursor_across_reconnects() -> None:
    """After receiving seq=7 the next request should use since=7."""
    requests_seen: list[str] = []

    intent = {
        "intent_id": "dd-4",
        "seq": 7,
        "event_type": "intent.submitted",
        "status": "SUBMITTED",
        "at": "2026-03-01T00:00:00Z",
    }
    intent2 = {
        "intent_id": "ee-5",
        "seq": 8,
        "event_type": "intent.submitted",
        "status": "SUBMITTED",
        "at": "2026-03-01T00:00:01Z",
    }

    def handler(request: httpx.Request) -> httpx.Response:
        since_param = request.url.params.get("since", "?")
        requests_seen.append(since_param)
        call_no = len(requests_seen)
        if call_no == 1:
            # first call: deliver intent with seq=7 + keepalive
            return httpx.Response(
                200,
                text=_sse([("intent.submitted", intent)]) + "event: stream.timeout\ndata: {}\n\n",
            )
        # second call: deliver second intent so we can consume it
        return httpx.Response(
            200,
            text=_sse([("intent.submitted", intent2)]) + "event: stream.timeout\ndata: {}\n\n",
        )

    client = _client(handler)
    gen = client.listen("org/ws/bot")
    e1 = next(gen)
    assert e1["seq"] == 7
    e2 = next(gen)
    assert e2["seq"] == 8
    # the reconnect should use since=7
    assert requests_seen[0] == "0"
    assert requests_seen[1] == "7"


def test_listen_raises_on_empty_address() -> None:
    client = _client(lambda r: httpx.Response(200, text=""))
    with pytest.raises(ValueError, match="address must be a non-empty string"):
        list(client.listen(""))


def test_listen_raises_on_negative_since() -> None:
    client = _client(lambda r: httpx.Response(200, text=""))
    with pytest.raises(ValueError, match="since must be >= 0"):
        list(client.listen("org/ws/bot", since=-1))


def test_listen_raises_on_invalid_wait_seconds() -> None:
    client = _client(lambda r: httpx.Response(200, text=""))
    with pytest.raises(ValueError, match="wait_seconds must be >= 1"):
        list(client.listen("org/ws/bot", wait_seconds=0))


def test_listen_raises_timeout_error_when_deadline_exceeded() -> None:
    import time as _time

    def handler(request: httpx.Request) -> httpx.Response:
        # Simulate a short server delay so we don't spin too tight
        _time.sleep(0.05)
        return httpx.Response(200, text="event: stream.timeout\ndata: {}\n\n")

    client = _client(handler)
    with pytest.raises(TimeoutError):
        list(client.listen("org/ws/bot", timeout_seconds=0.12))


def test_listen_requires_api_key() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if not request.headers.get("x-api-key"):
            return httpx.Response(401, json={"error": "Unauthorized"})
        intent = {"intent_id": "x1", "seq": 1, "event_type": "intent.submitted", "status": "SUBMITTED", "at": "2026-03-01T00:00:00Z"}
        return httpx.Response(200, text=_sse([("intent.submitted", intent)]) + "event: stream.timeout\ndata: {}\n\n")

    client = _client(handler, api_key="my-api-key")
    # should succeed — consume one event without raising auth error
    result = next(client.listen("org/ws/bot"))
    assert result["intent_id"] == "x1"


def test_listen_raises_auth_error_on_401() -> None:
    from axme.exceptions import AxmeAuthError

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(401, json={"error": "Unauthorized"})

    client = _client(handler)
    with pytest.raises(AxmeAuthError):
        list(client.listen("org/ws/bot"))


# ------------------------------------------------------------------
# Session API tests
# ------------------------------------------------------------------


def test_create_session() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.method == "POST"
        assert request.url.path == "/v1/sessions"
        body = json.loads(request.content)
        assert body["type"] == "task"
        assert body["metadata"]["agent"] == "claude-code"
        return httpx.Response(200, json={
            "ok": True,
            "session_id": "s-123",
            "status": "ACTIVE",
            "type": "task",
            "created_at": "2026-03-26T12:00:00Z",
        })

    client = _client(handler)
    result = client.create_session(type="task", metadata={"agent": "claude-code"})
    assert result["ok"] is True
    assert result["session_id"] == "s-123"
    assert result["status"] == "ACTIVE"


def test_create_session_with_depends_on() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        assert body["depends_on"] == ["s-dep-1", "s-dep-2"]
        return httpx.Response(200, json={"ok": True, "session_id": "s-456", "status": "PAUSED", "type": "task", "created_at": "2026-03-26T12:00:00Z"})

    client = _client(handler)
    result = client.create_session(depends_on=["s-dep-1", "s-dep-2"])
    assert result["status"] == "PAUSED"


def test_get_session() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.method == "GET"
        assert request.url.path == "/v1/sessions/s-123"
        return httpx.Response(200, json={
            "ok": True,
            "session": {
                "session_id": "s-123",
                "type": "task",
                "status": "ACTIVE",
                "metadata": {"agent": "claude-code"},
            },
        })

    client = _client(handler)
    result = client.get_session("s-123")
    assert result["session"]["session_id"] == "s-123"


def test_list_sessions() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.method == "GET"
        assert request.url.path == "/v1/sessions"
        assert "status=ACTIVE" in str(request.url)
        return httpx.Response(200, json={"ok": True, "sessions": [{"session_id": "s-1"}, {"session_id": "s-2"}]})

    client = _client(handler)
    result = client.list_sessions(status="ACTIVE")
    assert len(result["sessions"]) == 2


def test_post_session_message() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.method == "POST"
        assert "/messages" in request.url.path
        body = json.loads(request.content)
        assert body["role"] == "agent"
        assert body["content"] == "Reading file..."
        return httpx.Response(200, json={"ok": True, "message_id": "m-1", "seq": 1, "created_at": "2026-03-26T12:00:00Z"})

    client = _client(handler)
    result = client.post_session_message("s-123", role="agent", content="Reading file...")
    assert result["ok"] is True
    assert result["seq"] == 1


def test_post_session_message_structured_content() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        assert body["content_type"] == "tool_use"
        assert body["content"]["tool"] == "Read"
        return httpx.Response(200, json={"ok": True, "message_id": "m-2", "seq": 2, "created_at": "2026-03-26T12:00:00Z"})

    client = _client(handler)
    result = client.post_session_message(
        "s-123", role="agent", content_type="tool_use",
        content={"tool": "Read", "input": {"path": "/tmp/foo.py"}},
    )
    assert result["ok"] is True


def test_list_session_messages() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.method == "GET"
        assert "/messages" in request.url.path
        return httpx.Response(200, json={"ok": True, "messages": [
            {"message_id": "m-1", "seq": 1, "role": "agent", "content": "Hello"},
        ]})

    client = _client(handler)
    result = client.list_session_messages("s-123")
    assert len(result["messages"]) == 1


def test_list_session_messages_with_since() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert "since=5" in str(request.url)
        return httpx.Response(200, json={"ok": True, "messages": []})

    client = _client(handler)
    result = client.list_session_messages("s-123", since=5)
    assert result["messages"] == []


def test_get_session_feed() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/v1/sessions/s-123/feed"
        return httpx.Response(200, json={"ok": True, "feed": [
            {"type": "message", "role": "agent", "content": "Working..."},
            {"type": "intent", "intent_id": "i-1", "status": "WAITING"},
        ]})

    client = _client(handler)
    result = client.get_session_feed("s-123")
    assert len(result["feed"]) == 2
    assert result["feed"][0]["type"] == "message"
    assert result["feed"][1]["type"] == "intent"


def test_complete_session() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.method == "POST"
        assert request.url.path == "/v1/sessions/s-123/complete"
        body = json.loads(request.content)
        assert body["result"]["pr_url"] == "https://github.com/org/repo/pull/42"
        return httpx.Response(200, json={"ok": True, "session_id": "s-123", "status": "COMPLETED"})

    client = _client(handler)
    result = client.complete_session("s-123", result={"pr_url": "https://github.com/org/repo/pull/42"})
    assert result["status"] == "COMPLETED"


def test_complete_session_no_result() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        assert "result" not in body
        return httpx.Response(200, json={"ok": True, "session_id": "s-123", "status": "COMPLETED"})

    client = _client(handler)
    result = client.complete_session("s-123")
    assert result["ok"] is True


def test_listen_session_stream() -> None:
    sse_body = (
        "event: session.message\n"
        'data: {"message_id": "m-1", "seq": 1, "role": "agent", "content": "Working..."}\n'
        "\n"
        "event: session.completed\n"
        'data: {"session_id": "s-123", "status": "COMPLETED"}\n'
        "\n"
    )

    def handler(request: httpx.Request) -> httpx.Response:
        assert "/feed/stream" in request.url.path
        return httpx.Response(200, text=sse_body, headers={"content-type": "text/event-stream"})

    client = _client(handler)
    events = list(client.listen_session("s-123", wait_seconds=2, timeout_seconds=5))
    assert len(events) == 2
    assert events[0]["type"] == "session.message"
    assert events[0]["content"] == "Working..."
    assert events[1]["type"] == "session.completed"


def test_listen_session_reconnects_on_timeout() -> None:
    call_count = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            sse_body = (
                "event: session.message\n"
                'data: {"message_id": "m-1", "seq": 1, "role": "agent", "content": "First"}\n'
                "\n"
                "event: stream.timeout\n"
                'data: {"ok": true, "last_seq": 1}\n'
                "\n"
            )
            return httpx.Response(200, text=sse_body, headers={"content-type": "text/event-stream"})
        else:
            sse_body = (
                "event: session.completed\n"
                'data: {"session_id": "s-123", "status": "COMPLETED"}\n'
                "\n"
            )
            return httpx.Response(200, text=sse_body, headers={"content-type": "text/event-stream"})

    client = _client(handler)
    events = list(client.listen_session("s-123", wait_seconds=1, poll_interval_seconds=0.01, timeout_seconds=10))
    assert len(events) == 2
    assert events[0]["content"] == "First"
    assert events[1]["type"] == "session.completed"
    assert call_count == 2
