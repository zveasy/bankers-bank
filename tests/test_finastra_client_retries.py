import os
import pytest

import bankersbank.finastra as fin


class _DummyResp:
    def __init__(self, status_code=200, json_data=None):
        self.status_code = status_code
        self._json = json_data if json_data is not None else {}
        self.ok = 200 <= status_code < 300
        self.text = ""
        self.headers = {}

    def json(self):
        return self._json

    def raise_for_status(self):
        if not self.ok:
            import requests
            raise requests.HTTPError(response=self)


def test_request_retries_with_backoff(monkeypatch):
    # Ensure normal (non-mock) branch so FinastraAPIClient uses Session.request
    monkeypatch.setenv("USE_MOCK_BALANCES", "false")

    # Fake token provider
    class _Prov:
        def fetch(self):
            return "TKN"

    # Capture attempts and simulate 2x 502 then success
    attempts = {"n": 0}

    def fake_request(self, method, url, headers=None, timeout=None, verify=True, **kwargs):
        attempts["n"] += 1
        if attempts["n"] < 3:
            return _DummyResp(status_code=502)
        return _DummyResp(status_code=200, json_data={"ok": True})

    # Avoid slow sleeps during test
    monkeypatch.setattr(fin.time, "sleep", lambda s: None)
    monkeypatch.setattr(fin.requests.Session, "request", fake_request, raising=True)

    client = fin.FinastraAPIClient(
        base_url=os.getenv("FINASTRA_BASE_URL", "https://api.fusionfabric.cloud"),
        tenant=os.getenv("FINASTRA_TENANT", "sandbox"),
        token_provider=_Prov(),
    )

    data = client.get_json("/collaterals")
    assert data == {"ok": True}
    assert attempts["n"] == 3
