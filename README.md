# axme-sdk-python

Official Python SDK for Axme APIs and workflows.

Canonical protocol positioning:

- **AXP is the Intent Protocol (durable execution layer).**

## Status

Initial v1 skeleton in progress.

## Quickstart

```python
from axme_sdk import AxmeClient, AxmeClientConfig

config = AxmeClientConfig(
    base_url="https://gateway.example.com",
    api_key="YOUR_API_KEY",
    max_retries=2,
    retry_backoff_seconds=0.2,
)

with AxmeClient(config) as client:
    print(client.health(trace_id="trace-quickstart-001"))
    result = client.create_intent(
        {
            "intent_type": "notify.message.v1",
            "from_agent": "agent://example/sender",
            "to_agent": "agent://example/receiver",
            "payload": {"text": "hello"},
        },
        correlation_id="11111111-1111-1111-1111-111111111111",
        idempotency_key="create-intent-001",
    )
    print(result)
    print(client.get_intent(result["intent_id"])["intent"]["status"])
    inbox = client.list_inbox(owner_agent="agent://example/receiver", trace_id="trace-inbox-001")
    print(inbox)
    thread = client.get_inbox_thread("11111111-1111-4111-8111-111111111111", owner_agent="agent://example/receiver")
    print(thread["thread"]["status"])
    changes = client.list_inbox_changes(owner_agent="agent://example/receiver", limit=50)
    print(changes["next_cursor"], changes["has_more"])
    replied = client.reply_inbox_thread(
        "11111111-1111-4111-8111-111111111111",
        message="Acknowledged",
        owner_agent="agent://example/receiver",
        idempotency_key="reply-001",
    )
    print(replied)
    delegated = client.delegate_inbox_thread(
        "11111111-1111-4111-8111-111111111111",
        {"delegate_to": "agent://example/delegate", "note": "handoff"},
        owner_agent="agent://example/receiver",
        idempotency_key="delegate-001",
    )
    print(delegated["thread"]["status"])
    approved = client.approve_inbox_thread(
        "11111111-1111-4111-8111-111111111111",
        {"comment": "approved"},
        owner_agent="agent://example/receiver",
        idempotency_key="approve-001",
    )
    print(approved["thread"]["status"])
    rejected = client.reject_inbox_thread(
        "11111111-1111-4111-8111-111111111111",
        {"comment": "rejected"},
        owner_agent="agent://example/receiver",
        idempotency_key="reject-001",
    )
    print(rejected["thread"]["status"])
    deleted = client.delete_inbox_messages(
        "11111111-1111-4111-8111-111111111111",
        {"mode": "self", "limit": 1},
        owner_agent="agent://example/receiver",
        idempotency_key="delete-001",
    )
    print(deleted["deleted_count"])
    approval = client.decide_approval(
        "55555555-5555-4555-8555-555555555555",
        decision="approve",
        comment="Looks good",
        idempotency_key="approval-001",
    )
    print(approval["approval"]["decision"])
    capabilities = client.get_capabilities()
    print(capabilities["supported_intent_types"])
    invite = client.create_invite(
        {"owner_agent": "agent://example/receiver", "recipient_hint": "Partner A", "ttl_seconds": 3600},
        idempotency_key="invite-create-001",
    )
    print(invite["token"])
    invite_details = client.get_invite(invite["token"])
    print(invite_details["status"])
    accepted = client.accept_invite(
        invite["token"],
        {"nick": "@PartnerA.User", "display_name": "Partner A"},
        idempotency_key="invite-accept-001",
    )
    print(accepted["public_address"])
    media_upload = client.create_media_upload(
        {
            "owner_agent": "agent://example/receiver",
            "filename": "contract.pdf",
            "mime_type": "application/pdf",
            "size_bytes": 12345,
        },
        idempotency_key="media-create-001",
    )
    print(media_upload["upload_id"])
    media_state = client.get_media_upload(media_upload["upload_id"])
    print(media_state["upload"]["status"])
    finalized = client.finalize_media_upload(
        {"upload_id": media_upload["upload_id"], "size_bytes": 12345},
        idempotency_key="media-finalize-001",
    )
    print(finalized["status"])
    schema = client.upsert_schema(
        {
            "semantic_type": "axme.calendar.schedule.v1",
            "schema_json": {"type": "object", "required": ["date"], "properties": {"date": {"type": "string"}}},
            "compatibility_mode": "strict",
        },
        idempotency_key="schema-upsert-001",
    )
    print(schema["schema"]["schema_hash"])
    schema_get = client.get_schema("axme.calendar.schedule.v1")
    print(schema_get["schema"]["semantic_type"])
    registered = client.register_nick(
        {"nick": "@partner.user", "display_name": "Partner User"},
        idempotency_key="nick-register-001",
    )
    print(registered["owner_agent"])
    nick_check = client.check_nick("@partner.user")
    print(nick_check["available"])
    renamed = client.rename_nick(
        {"owner_agent": registered["owner_agent"], "nick": "@partner.new"},
        idempotency_key="nick-rename-001",
    )
    print(renamed["public_address"])
    profile = client.get_user_profile(registered["owner_agent"])
    print(profile["updated_at"])
    profile_updated = client.update_user_profile(
        {"owner_agent": registered["owner_agent"], "display_name": "Partner User Updated"},
        idempotency_key="profile-update-001",
    )
    print(profile_updated["display_name"])
    subscription = client.upsert_webhook_subscription(
        {
            "callback_url": "https://integrator.example/webhooks/axme",
            "event_types": ["inbox.thread_created"],
            "active": True,
        }
    )
    print(subscription)
    events = client.publish_webhook_event(
        {"event_type": "inbox.thread_created", "source": "sdk-example", "payload": {"thread_id": "t-1"}},
        owner_agent="agent://example/receiver",
    )
    print(events["event_id"])
    mcp_info = client.mcp_initialize()
    print(mcp_info["protocolVersion"])
    tools = client.mcp_list_tools()
    print(len(tools.get("tools", [])))
    mcp_result = client.mcp_call_tool(
        "axme.send",
        arguments={"to": "agent://example/receiver", "text": "hello from MCP"},
        owner_agent="agent://example/receiver",
        idempotency_key="mcp-send-001",
    )
    print(mcp_result.get("status"))
```

## Development

```bash
python -m pip install -e ".[dev]"
pytest
```
