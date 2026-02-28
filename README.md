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
```

## Development

```bash
python -m pip install -e ".[dev]"
pytest
```
