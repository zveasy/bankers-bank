# tests/test_finastra_client.py
import os
import json
import pytest

from bankersbank.finastra import (
    ClientCredentialsTokenProvider,
    FinastraAPIClient,
)

class _DummyResp:
    def __init__(self, status_code=200, json_data=None, text="", headers=None, content=True):
        self.status_code = status_code
        self._json_data = json_data if json_data is not None else {}
        self.text = text or (json.dumps(self._json_data) if self._json_data else "")
        self.headers = headers or {}
        self.ok = 200 <= status_code < 300
        self.content = b"{}" if content else b""

    def json(self):
        return self._json_data

    def raise_for_status(self):
        if not self.ok:
            class _E(Exception): ...
            raise requests.HTTPError(response=self)  # type: ignore[name-defined]

def test_token_provider_caches_and_refreshes(monkeypatch):
    base_url = "https://api.fusionfabric.cloud"
    tenant = "sandbox"
    client_id = "abc"
    client_secret = "xyz"
    scope = "accounts"

    now = [1_000_000]

    def fake_time():
        return now[0]

    calls = {"post": 0}

    def fake_requests_post(url, headers=None, data=None, timeout=None, verify=True):
        calls["post"] += 1
        return _DummyResp(
            status_code=200,
            json_data={"access_token": f"TOKEN_{calls['post']}", "expires_in": 2},
        )

    import bankersbank.finastra as fin
    monkeypatch.setattr(fin.requests, "post", fake_requests_post)
    monkeypatch.setattr(fin.time, "time", fake_time)

    tp = ClientCredentialsTokenProvider(
        base_url=base_url,
        tenant=tenant,
        client_id=client_id,
        client_secret=client_secret,
        scope=scope,
    )

    t1 = tp.fetch()
    assert t1 == "TOKEN_1"
    assert calls["post"] == 1

    t2 = tp.fetch()
    assert t2 == "TOKEN_1"
    assert calls["post"] == 1

    now[0] += 5
    t3 = tp.fetch()
    assert t3 == "TOKEN_2"
    assert calls["post"] == 2

def test_client_injects_bearer_and_returns_json(monkeypatch):
    class FakeProvider:
        def fetch(self): return "BEARER_TOKEN"

    captured = {"headers": None, "url": None, "method": None}

    def fake_request(self, method, url, **kwargs):
        captured["headers"] = kwargs.get("headers", {})
        captured["url"] = url
        captured["method"] = method
        return _DummyResp(status_code=200, json_data={"ok": True, "url": url})

    client = FinastraAPIClient(
        base_url="https://api.fusionfabric.cloud",
        tenant="sandbox",
        product="total-lending/collaterals/b2b/v2",
        token_provider=FakeProvider(),
    )

    import bankersbank.finastra as fin
    monkeypatch.setattr(fin.requests.Session, "request", fake_request, raising=True)

    data = client.get_json("/collaterals")
    assert data["ok"] is True
    assert "Authorization" in captured["headers"]
    assert captured["headers"]["Authorization"] == "Bearer BEARER_TOKEN"
    assert captured["method"] == "GET"
    assert "/total-lending/collaterals/b2b/v2/collaterals" in captured["url"]

@pytest.mark.skipif(
    not all(os.getenv(k) for k in ("FINASTRA_CLIENT_ID", "FINASTRA_CLIENT_SECRET")),
    reason="Live Finastra creds not provided in environment",
)
def test_live_list_collaterals_smoke():
    base_url = os.getenv("FINASTRA_BASE_URL", "https://api.fusionfabric.cloud")
    tenant = os.getenv("FINASTRA_TENANT", "sandbox")
    product = os.getenv("FINASTRA_PRODUCT_COLLATERAL", "total-lending/collaterals/b2b/v2")

    provider = ClientCredentialsTokenProvider(
        base_url=base_url,
        tenant=tenant,
        client_id=os.environ["FINASTRA_CLIENT_ID"],
        client_secret=os.environ["FINASTRA_CLIENT_SECRET"],
        scope="accounts",
    )
    client = FinastraAPIClient(
        base_url=base_url,
        tenant=tenant,
        product=product,
        token_provider=provider,
    )

    resp = client.get_json("/collaterals?startingIndex=0&pageSize=5")
    assert "items" in resp
    assert isinstance(resp["items"], list)
