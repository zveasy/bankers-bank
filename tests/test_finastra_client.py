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

    import importlib
    import prometheus_client as _prom
    _prom.REGISTRY = _prom.CollectorRegistry()
    import bankersbank.finastra as fin
    fin = importlib.reload(fin)
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
    # Ensure real URL building (not mock short-circuit)
    monkeypatch.setenv("USE_MOCK_BALANCES", "false")
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


def _get_counter_value(metric, labels: dict) -> float:
    # Iterate over collected samples to find matching labelset
    total = 0.0
    for family in metric.collect():
        for sample in family.samples:
            # sample.name like 'finastra_api_calls_total'
            if sample.name.endswith("_total"):
                if all(sample.labels.get(k) == v for k, v in labels.items()):
                    total += float(sample.value)
    return total


def test_api_metrics_success_increment(monkeypatch):
    # Ensure non-mock path so product prefix is used in endpoint label
    monkeypatch.setenv("USE_MOCK_BALANCES", "false")
    import bankersbank.finastra as fin

    # Fake a successful response via session.request
    def fake_request(self, method, url, **kwargs):
        return _DummyResp(status_code=200, json_data={"ok": True})

    # Mock token endpoint to return a bearer
    def fake_post(url, headers=None, data=None, timeout=None, verify=True):
        return _DummyResp(status_code=200, json_data={"access_token": "TOK", "expires_in": 300})

    monkeypatch.setattr(fin.requests, "post", fake_post, raising=True)
    monkeypatch.setattr(fin.requests.Session, "request", fake_request, raising=True)

    client = FinastraAPIClient(
        base_url="https://api.fusionfabric.cloud",
        tenant="sandbox",
        product="total-lending/collaterals/b2b/v2",
        token_provider=ClientCredentialsTokenProvider(token_url="https://auth/token", client_id="x", client_secret="y", scope="openid"),
    )
    # Enable breaker on instance (avoid module reload & prometheus duplication)
    client._cb_enabled = True
    client._cb_fail_threshold = 2
    client._cb_cooldown = 60.0
    
    endpoint = "total-lending/collaterals/b2b/v2:/collaterals"
    before = _get_counter_value(fin._api_calls_total, {"endpoint": endpoint, "status": "200"})
    client.get_json("/collaterals")
    after = _get_counter_value(fin._api_calls_total, {"endpoint": endpoint, "status": "200"})
    assert after == before + 1


def _mock_token_ok(monkeypatch):
    import bankersbank.finastra as fin
    def fake_post(url, headers=None, data=None, timeout=None, verify=True):
        return _DummyResp(status_code=200, json_data={"access_token": "TOK", "expires_in": 300})
    monkeypatch.setattr(fin.requests, "post", fake_post, raising=True)


def test_circuit_breaker_trips_and_blocks(monkeypatch):
    # Enable breaker with low threshold and long cooldown
    monkeypatch.setenv("FEATURE_FINASTRA_BREAKER", "1")
    monkeypatch.setenv("FINASTRA_BREAKER_FAIL_THRESHOLD", "2")
    monkeypatch.setenv("FINASTRA_BREAKER_COOLDOWN_SEC", "60")
    monkeypatch.setenv("USE_MOCK_BALANCES", "false")
    import bankersbank.finastra as fin
    _mock_token_ok(monkeypatch)

    # Count how many times session.request is actually attempted
    calls = {"n": 0}
    class _R:
        ok = False
        status_code = 502
        text = "bad gateway"
        headers = {}
        def raise_for_status(self):
            import requests
            raise requests.HTTPError(response=self)
    def fail_request(self, method, url, **kwargs):
        calls["n"] += 1
        return _R()
    monkeypatch.setattr(fin.time, "sleep", lambda *_: None)
    monkeypatch.setattr(fin.requests.Session, "request", fail_request, raising=True)

    # Fix time so breaker open window persists
    t0 = [1_000_000.0]
    monkeypatch.setattr(fin.time, "time", lambda: t0[0])

    client = FinastraAPIClient(
        base_url="https://api.fusionfabric.cloud",
        tenant="sandbox",
        product="total-lending/collaterals/b2b/v2",
        token_provider=ClientCredentialsTokenProvider(token_url="https://auth/token", client_id="x", client_secret="y", scope="openid"),
    )

    import pytest as _pytest
    # First call: fails after retries (transient) and trips counter 1
    with _pytest.raises(Exception):
        client.get_json("/collaterals")
    # Second call: fails and should trip breaker to open
    with _pytest.raises(Exception):
        client.get_json("/collaterals")
    # Ensure breaker is open
    assert getattr(client, "_cb_state") in ("open", "half",)
    # Third call: since cooldown not elapsed and breaker open, should fast-fail without calling request
    before_calls = calls["n"]
    with _pytest.raises(RuntimeError, match="circuit_open"):
        client.get_json("/collaterals")
    assert calls["n"] == before_calls  # no additional underlying HTTP attempt


def test_circuit_breaker_half_open_allows_success(monkeypatch):
    # Enable breaker
    monkeypatch.setenv("FEATURE_FINASTRA_BREAKER", "1")
    monkeypatch.setenv("FINASTRA_BREAKER_FAIL_THRESHOLD", "1")
    monkeypatch.setenv("FINASTRA_BREAKER_COOLDOWN_SEC", "10")
    monkeypatch.setenv("USE_MOCK_BALANCES", "false")
    import bankersbank.finastra as fin
    _mock_token_ok(monkeypatch)

    # First fail to open breaker
    class _Rfail:
        ok = False
        status_code = 502
        text = "bad gateway"
        headers = {}
        def raise_for_status(self):
            import requests
            raise requests.HTTPError(response=self)
    # Then success
    def success_request(self, method, url, **kwargs):
        return _DummyResp(status_code=200, json_data={"ok": True})

    # Control time to move through states
    t0 = [1_000_000.0]
    monkeypatch.setattr(fin.time, "time", lambda: t0[0])
    monkeypatch.setattr(fin.time, "sleep", lambda *_: None)

    attempts = {"stage": "fail"}
    def flip_request(self, method, url, **kwargs):
        if attempts["stage"] == "fail":
            return _Rfail()
        return success_request(self, method, url, **kwargs)
    monkeypatch.setattr(fin.requests.Session, "request", flip_request, raising=True)

    client = FinastraAPIClient(
        base_url="https://api.fusionfabric.cloud",
        tenant="sandbox",
        product="total-lending/collaterals/b2b/v2",
        token_provider=ClientCredentialsTokenProvider(token_url="https://auth/token", client_id="x", client_secret="y", scope="openid"),
    )

    import pytest as _pytest
    # Trip breaker
    with _pytest.raises(Exception):
        client.get_json("/collaterals")
    # Now in open; advance time to beyond cooldown to enter half-open
    t0[0] += 20
    # Flip to success for trial
    attempts["stage"] = "ok"
    # Should succeed (half-open -> closed)
    data = client.get_json("/collaterals")
    assert data["ok"] is True
    # Subsequent call should also succeed
    data2 = client.get_json("/collaterals")
    assert data2["ok"] is True


def test_retry_pacing_applied(monkeypatch):
    # Configure pacing so each retry adds a tiny fixed sleep after backoff
    monkeypatch.setenv("FINASTRA_RETRY_MIN_SLEEP_MS", "50")
    monkeypatch.setenv("USE_MOCK_BALANCES", "false")
    import bankersbank.finastra as fin
    _mock_token_ok(monkeypatch)

    sleeps = []
    def fake_sleep(sec):
        sleeps.append(sec)
    monkeypatch.setattr(fin.time, "sleep", fake_sleep)

    class _R:
        ok = False
        status_code = 502
        text = "bad gateway"
        headers = {}
        def raise_for_status(self):
            import requests
            raise requests.HTTPError(response=self)
    def fail_request(self, method, url, **kwargs):
        return _R()
    monkeypatch.setattr(fin.requests.Session, "request", fail_request, raising=True)

    client = FinastraAPIClient(
        base_url="https://api.fusionfabric.cloud",
        tenant="sandbox",
        product="total-lending/collaterals/b2b/v2",
        token_provider=ClientCredentialsTokenProvider(token_url="https://auth/token", client_id="x", client_secret="y", scope="openid"),
    )

    import pytest as _pytest
    with _pytest.raises(Exception):
        client.get_json("/collaterals")
    # We expect at least one pacing sleep of ~0.05s present
    assert any(s >= 0.045 for s in sleeps)


def test_api_metrics_failure_increment(monkeypatch):
    # Ensure non-mock path and speed retry sleeps
    monkeypatch.setenv("USE_MOCK_BALANCES", "false")
    import bankersbank.finastra as fin
    monkeypatch.setattr(fin.time, "sleep", lambda *_: None)

    class _R:
        ok = False
        status_code = 502
        text = "bad gateway"
        headers = {}

        def raise_for_status(self):
            import requests
            raise requests.HTTPError(response=self)

    def fail_request(self, method, url, **kwargs):
        return _R()

    # Mock token endpoint to return a bearer so request() runs and fails with 502
    def fake_post(url, headers=None, data=None, timeout=None, verify=True):
        return _DummyResp(status_code=200, json_data={"access_token": "TOK", "expires_in": 300})

    monkeypatch.setattr(fin.requests, "post", fake_post, raising=True)
    monkeypatch.setattr(fin.requests.Session, "request", fail_request, raising=True)

    client = FinastraAPIClient(
        base_url="https://api.fusionfabric.cloud",
        tenant="sandbox",
        product="total-lending/collaterals/b2b/v2",
        token_provider=ClientCredentialsTokenProvider(token_url="https://auth/token", client_id="x", client_secret="y", scope="openid"),
    )

    endpoint = "total-lending/collaterals/b2b/v2:/collaterals"
    before = _get_counter_value(fin._api_calls_total, {"endpoint": endpoint, "status": "502"})
    import pytest as _pytest
    with _pytest.raises(Exception):
        client.get_json("/collaterals")
    after = _get_counter_value(fin._api_calls_total, {"endpoint": endpoint, "status": "502"})
    assert after == before + 1

@pytest.mark.skipif(
    not (
        (os.getenv("FINASTRA_CLIENT_ID") and os.getenv("FINASTRA_CLIENT_SECRET"))
        or (os.getenv("FINASTRA_B2B_CLIENT_ID") and os.getenv("FINASTRA_B2B_CLIENT_SECRET"))
    ),
    reason="Live Finastra creds not provided in environment",
)
def test_live_list_collaterals_smoke():
    # Prefer AUTH URL host to avoid passing a product-specific URL into token provider
    auth_url = os.getenv("FINASTRA_AUTH_URL")
    if auth_url:
        try:
            from urllib.parse import urlparse
            p = urlparse(auth_url)
            base_url = f"{p.scheme}://{p.netloc}"
        except Exception:
            base_url = os.getenv("FINASTRA_BASE_URL", "https://api.fusionfabric.cloud")
    else:
        base_url = (
            os.getenv("FINASTRA_BASE_URL")
            or "https://api.fusionfabric.cloud"
        )
    tenant = os.getenv("FINASTRA_TENANT", "sandbox")
    product = os.getenv("FINASTRA_PRODUCT_COLLATERAL", "total-lending/collaterals/b2b/v2")

    client_id = os.getenv("FINASTRA_CLIENT_ID") or os.getenv("FINASTRA_B2B_CLIENT_ID")
    client_secret = os.getenv("FINASTRA_CLIENT_SECRET") or os.getenv("FINASTRA_B2B_CLIENT_SECRET")

    provider = ClientCredentialsTokenProvider(
        base_url=base_url,
        tenant=tenant,
        client_id=client_id,
        client_secret=client_secret,
        scope=os.getenv("FINASTRA_SCOPE", "openid"),
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
