from __future__ import annotations

import json

import httpx
import pytest

from axme_sdk import AxmeClient, AxmeClientConfig
from axme_sdk.exceptions import AxmeAuthError, AxmeHttpError, AxmeRateLimitError, AxmeValidationError


def _transport(handler):
    return httpx.MockTransport(handler)


def _client(
    handler,
    api_key: str = "token",
    *,
    max_retries: int = 2,
    retry_backoff_seconds: float = 0.0,
    auto_trace_id: bool = True,
) -> AxmeClient:
    cfg = AxmeClientConfig(
        base_url="https://api.axme.test",
        api_key=api_key,
        max_retries=max_retries,
        retry_backoff_seconds=retry_backoff_seconds,
        auto_trace_id=auto_trace_id,
    )
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
        assert request.headers["Authorization"] == "Bearer token"
        return httpx.Response(200, json={"ok": True})

    client = _client(handler)
    assert client.health() == {"ok": True}


def test_health_propagates_trace_id_header() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.headers.get("x-trace-id") == "trace-123"
        return httpx.Response(200, json={"ok": True})

    client = _client(handler, auto_trace_id=False)
    assert client.health(trace_id="trace-123") == {"ok": True}


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
                    "status": "accepted",
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
                "intent": {"intent_id": intent_id, "status": "done"},
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
        assert request.read() == b'{"message":"ack"}'
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
        assert request.read() == b'{"decision":"approve","comment":"approved"}'
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
        assert request.read() == b'{"callback_url":"https://integrator.example/webhooks/axme","event_types":["inbox.thread_created"],"active":true}'
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
            "Authorization": f"Bearer {cfg.api_key}",
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
