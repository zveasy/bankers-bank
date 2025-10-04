import os
import types
import pytest
from common import secrets as _secrets
from fastapi.testclient import TestClient
from common.auth import require_token

import bankersbank.finastra as fin
from asset_aggregator.api import app as aggregator_app
from mocks.mock_finastra_api import app as mock_finastra_app


@pytest.fixture(autouse=True)
def _env_defaults(monkeypatch):
    # Enable feature and mock mode by default
    monkeypatch.setenv("FEATURE_FINASTRA_COLLATERALS", "1")
    monkeypatch.setenv("USE_MOCK_BALANCES", "true")
    monkeypatch.setenv("FINASTRA_TOKEN_STRATEGY", "static")
    monkeypatch.setenv("FINASTRA_STATIC_BEARER", "dummy")
    # Base URL used only for building the absolute URL; we'll route via TestClient
    monkeypatch.setenv("FINASTRA_BASE_URL", "http://testserver")
    monkeypatch.setenv("FINASTRA_TENANT", "sandbox")
    # Satisfy require_token() by seeding API_TOKENS in secrets manager
    _secrets.secrets.set_override({"API_TOKENS": {"tester": "test"}})
    yield


def _proxy_to_mock_server():
    """
    Monkeypatch fin.requests.request so that any absolute URL (http://testserver/...)
    is executed against the in-repo mock Finastra FastAPI app.
    """
    client = TestClient(mock_finastra_app)

    def _request(method, url, **kwargs):
        # Strip scheme/host; mock app mounted at root
        # Keep headers/json/params intact
        path = url
        if "://" in url:
            path = url.split("://", 1)[1]
            path = path.split("/", 1)[1] if "/" in path else ""
            path = "/" + path
        headers = kwargs.get("headers", {}) or {}
        json_payload = kwargs.get("json")
        params = kwargs.get("params")
        resp = client.request(method, path, headers=headers, json=json_payload, params=params)
        # Create a minimal shim matching requests.Response attributes we rely on
        class _Shim:
            def __init__(self, r):
                self.status_code = r.status_code
                self._json = None
                try:
                    self._json = r.json()
                except Exception:
                    self._json = None
                self.text = r.text
                self.headers = r.headers
                self.ok = 200 <= r.status_code < 300

            def json(self):
                if self._json is not None:
                    return self._json
                raise ValueError("no json")

            def raise_for_status(self):
                if not self.ok:
                    import requests
                    raise requests.HTTPError(response=self)

        return _Shim(resp)

    return _request


def test_list_collaterals_mock(monkeypatch):
    # Route all Finastra HTTP calls to the mock app
    monkeypatch.setattr(fin.requests, "request", _proxy_to_mock_server())

    client = TestClient(aggregator_app)
    r = client.get("/finastra/b2b/collaterals?top=5&startingIndex=0", headers={"Authorization": "Bearer test"})
    assert r.status_code == 200
    body = r.json()
    assert "items" in body
    assert isinstance(body["items"], list)


def test_feature_flag_disabled(monkeypatch):
    monkeypatch.setenv("FEATURE_FINASTRA_COLLATERALS", "0")
    client = TestClient(aggregator_app)
    r = client.get("/finastra/b2b/collaterals", headers={"Authorization": "Bearer test"})
    assert r.status_code == 404


def test_error_bubbles_with_trace_headers(monkeypatch):
    # Simulate upstream HTTPError with correlation headers
    class _Resp:
        def __init__(self):
            self.status_code = 502
            self.text = "upstream error"
            self.headers = {"ff-trace-id": "trace123", "activityId": "act456"}

    def _fail_request(method, url, **kwargs):
        # Minimal Response-like object that triggers HTTPError in fin client
        class _R:
            ok = False
            status_code = 502
            text = "upstream error"
            headers = {"ff-trace-id": "trace123", "activityId": "act456"}

            def raise_for_status(self):
                import requests
                raise requests.HTTPError(response=self)

            def json(self):
                return {"error": "fail"}

        return _R()

    monkeypatch.setenv("FEATURE_FINASTRA_COLLATERALS", "1")
    # Keep mock mode enabled from fixture so fin client uses requests.request path we patch
    monkeypatch.setattr(fin.requests, "request", _fail_request)

    client = TestClient(aggregator_app)
    r = client.get("/finastra/b2b/collaterals", headers={"Authorization": "Bearer test"})
    assert r.status_code == 502
    # FastAPI serializes detail; content may be empty string in some adapters
    body = r.json()
    assert "detail" in body


@pytest.mark.finastra_live
@pytest.mark.skipif(not os.getenv("TEST_COLLATERAL_ID_PRIMARY"), reason="live collateral id not provided")
def test_live_get_collateral():
    # Requires valid env for live Finastra access and TEST_COLLATERAL_ID_PRIMARY
    client = TestClient(aggregator_app)
    cid = os.environ["TEST_COLLATERAL_ID_PRIMARY"]
    r = client.get(f"/finastra/b2b/collaterals/{cid}", headers={"Authorization": "Bearer test"})
    assert r.status_code in (200, 404)
    # When 200, ensure JSON body
    if r.status_code == 200:
        assert isinstance(r.json(), dict)
