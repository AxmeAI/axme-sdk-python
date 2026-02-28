# axme-sdk-python

Official Python SDK for Axme APIs and workflows.

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
    inbox = client.list_inbox(owner_agent="agent://example/receiver", trace_id="trace-inbox-001")
    print(inbox)
    changes = client.list_inbox_changes(owner_agent="agent://example/receiver", limit=50)
    print(changes["next_cursor"], changes["has_more"])
    replied = client.reply_inbox_thread(
        "11111111-1111-4111-8111-111111111111",
        message="Acknowledged",
        owner_agent="agent://example/receiver",
        idempotency_key="reply-001",
    )
    print(replied)
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
```

## Development

```bash
python -m pip install -e ".[dev]"
pytest
```
