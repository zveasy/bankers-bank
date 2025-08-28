import asyncio
import httpx
import pytest

from integrations.finastra.http import FinastraHTTP


class DummyProvider:
    """First call returns stale token; refresh gives new token."""

    def __init__(self):
        self.calls = 0
        self.refresh_calls = 0

    async def token(self):  # noqa: D401
        self.calls += 1
        if self.calls == 1:
            return "stale"
        return "fresh"

    async def refresh(self):  # noqa: D401
        self.refresh_calls += 1
        return "fresh"


class _Transport401Then200(httpx.AsyncBaseTransport):
    def __init__(self):
        self.calls = 0

    async def handle_async_request(self, request):  # type: ignore[override]
        self.calls += 1
        if self.calls == 1:
            return httpx.Response(401)
        return httpx.Response(200, json={"ok": True})


@pytest.mark.anyio
async def test_401_refresh_retry_success():
    provider = DummyProvider()
    transport = _Transport401Then200()

    http = FinastraHTTP(product="test", token_provider=provider, base_url="https://api.test", transport=transport)

    resp = await http.get("/whatever")
    assert resp.status_code == 200
    assert provider.refresh_calls == 1
    assert transport.calls == 2


class FreshProvider(DummyProvider):
    async def token(self):  # noqa: D401
        self.calls += 1
        return "fresh"

    async def refresh(self):  # noqa: D401
        self.refresh_calls += 1
        return "fresh"


class _Transport200(httpx.AsyncBaseTransport):
    async def handle_async_request(self, request):  # type: ignore[override]
        return httpx.Response(200)


@pytest.mark.anyio
async def test_no_refresh_if_token_fresh():
    provider = FreshProvider()
    transport = _Transport200()
    http = FinastraHTTP(product="test", token_provider=provider, base_url="https://api.test", transport=transport)
    resp = await http.get("/ping")
    assert resp.status_code == 200
    assert provider.refresh_calls == 0
