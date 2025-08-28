import asyncio
from types import SimpleNamespace

import httpx
import pytest

from common import secrets as secrets_module
from integrations.finastra.auth import (
    AuthCodeTokenProvider,
    ClientCredentialsTokenProvider,
)


class _MockTransport(httpx.AsyncBaseTransport):
    """Basic transport that returns pre-canned JSON body and counts calls."""

    def __init__(self, payload):
        self.payload = payload
        self.calls = 0

    async def handle_async_request(self, request):  # type: ignore[override]
        self.calls += 1
        return httpx.Response(200, json=self.payload)


@pytest.mark.anyio
async def test_client_credentials_provider(monkeypatch):
    # arrange env
    env = {
        "FINA_CLIENT_ID": "cid",
        "FINA_CLIENT_SECRET": "csecret",
        "FINA_TOKEN_URL": "https://example/token",
        "FINA_SCOPES_CC": "openid product",
    }
    secrets_module.secrets.update(env)

    transport = _MockTransport({"access_token": "tok123", "expires_in": 60})
    orig_client = httpx.AsyncClient

    def _mock_client(*args, **kw):
        kw["transport"] = transport
        return orig_client(*args, **kw)

    monkeypatch.setattr(httpx, "AsyncClient", _mock_client, raising=True)

    provider = ClientCredentialsTokenProvider()

    # act
    t1 = await provider.token()
    t2 = await provider.token()  # should come from cache, not hit transport

    # assert
    assert t1 == "tok123" == t2
    # only one HTTP call
    assert transport.calls == 1


@pytest.mark.anyio
async def test_authcode_provider(monkeypatch):
    env = {
        "FINA_CLIENT_ID": "cid",
        "FINA_CLIENT_SECRET": "csecret",
        "FINA_TOKEN_URL": "https://example/token",
        "FINA_REFRESH_TOKEN": "r1",
        "FINA_SCOPES_AUTHCODE": "openid product",
    }
    secrets_module.secrets.update(env)

    transport = _MockTransport(
        {"access_token": "tokABC", "refresh_token": "r2", "expires_in": 60}
    )
    orig_client = httpx.AsyncClient

    def _mock_client(*args, **kw):
        kw["transport"] = transport
        return orig_client(*args, **kw)

    monkeypatch.setattr(httpx, "AsyncClient", _mock_client, raising=True)

    provider = AuthCodeTokenProvider()

    t1 = await provider.token()
    t2 = await provider.token()

    assert t1 == "tokABC" == t2
    assert transport.calls == 1
