from __future__ import annotations

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


def test_health_success() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.method == "GET"
        assert request.url.path == "/health"
        assert request.headers["Authorization"] == "Bearer token"
        return httpx.Response(200, json={"ok": True})

    client = _client(handler)
    assert client.health() == {"ok": True}


def test_create_intent_success() -> None:
    payload = {"intent_type": "notify", "recipient": "agent://user/test"}

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.method == "POST"
        assert request.url.path == "/v1/intents"
        assert request.read() == b'{"intent_type":"notify","recipient":"agent://user/test"}'
        return httpx.Response(200, json={"intent_id": "it_123"})

    client = _client(handler)
    assert client.create_intent(payload) == {"intent_id": "it_123"}


def test_create_intent_raises_http_error() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(401, text="unauthorized")

    client = _client(handler, api_key="bad-token")

    with pytest.raises(AxmeHttpError) as exc_info:
        client.create_intent({"intent_type": "notify"})

    assert exc_info.value.status_code == 401
