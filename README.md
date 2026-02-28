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
)

with AxmeClient(config) as client:
    print(client.health())
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
```

## Development

```bash
python -m pip install -e ".[dev]"
pytest
```
