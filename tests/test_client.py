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
