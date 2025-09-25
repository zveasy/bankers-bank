"""Unit tests for Payments & Loans helpers in bankersbank.finastra.

These run fully offline by monkey-patching `requests.Session.request` so they
are CI-friendly.  Prometheus metrics are stubbed with minimal counter / hist
objects to assert increments without the real library.
"""
from __future__ import annotations

import uuid
from typing import Any, Dict

import pytest

import bankersbank.finastra as fin

# ---------------------------------------------------------------------------
# Test helpers
# ---------------------------------------------------------------------------

class _DummyResp:
    """Small stub that mimics `requests.Response` enough for our client."""

    def __init__(
        self,
        *,
        status_code: int = 200,
        json_data: Dict | None = None,
        text: str = "",
        headers: Dict | None = None,
        url: str = "http://example",
    ) -> None:
        self.status_code = status_code
        self._json_data = json_data or {}
        self.text = text or ""
        self.headers = headers or {}
        self.ok = 200 <= status_code < 300
        self.url = url
        self.reason = "OK" if self.ok else "Bad Gateway"

    def json(self):  # noqa: D401  (simple json helper)
        return self._json_data

    def raise_for_status(self):  # noqa: D401
        if not self.ok:
            import requests

            raise requests.HTTPError(
                f"{self.status_code} {self.reason} for url: {self.url}",
                response=self,
            )


def _fake_provider():
    class _Prov:
        def fetch(self):
            return "TEST_TOKEN"

    return _Prov()


# ---------------------------------------------------------------------------
# Retry configuration
# ---------------------------------------------------------------------------

def test_session_retries_configured(monkeypatch):
    """Verify Retry is wired for GET and 429/5xx status codes."""

    client = fin.FinastraAPIClient(token_provider=_fake_provider())
    https_adapter = client.session.adapters["https://"]
    retry_cfg = https_adapter.max_retries

    # 429 + common 5xx present
    assert {429, 500, 502, 503, 504}.issubset(set(retry_cfg.status_forcelist))

    allowed = set(
        getattr(retry_cfg, "allowed_methods", getattr(retry_cfg, "method_whitelist", set()))
    )
    assert {"GET", "HEAD", "OPTIONS"}.issubset(allowed)


# ---------------------------------------------------------------------------
# Payments: initiate
# ---------------------------------------------------------------------------

def test_payments_initiate_generates_x_request_id_and_metrics(monkeypatch):
    client = fin.FinastraAPIClient(token_provider=_fake_provider(), base_url="http://local")

    captured: Dict[str, Any] = {}

    def fake_request(self, method, url, **kwargs):  # noqa: D401
        captured.update(method=method, url=url, headers=kwargs.get("headers", {}), body=kwargs.get("json"))
        return _DummyResp(json_data={"paymentId": "p-123"}, url=url)

    monkeypatch.setattr(fin.requests.Session, "request", fake_request, raising=True)

    # Stub metrics ------------------------------------------------------
    class _Counter:
        def __init__(self):
            self.n = 0

        def labels(self, *_a, **_kw):
            return self

        def inc(self, v: int = 1):
            self.n += v
            return self

    class _Hist(_Counter):
        def observe(self, *_a, **_kw):
            self.inc()
            return self

    c_init = _Counter()
    c_non2xx = _Counter()
    h_lat = _Hist()

    monkeypatch.setattr(fin, "_payments_initiate_total", c_init)
    monkeypatch.setattr(fin, "_non_2xx_total", c_non2xx)
    monkeypatch.setattr(fin, "_latency_hist", h_lat)

    # Call under test ---------------------------------------------------
    payload = {"amount": {"value": "10.00", "currency": "USD"}}
    resp = client.payments_initiate(payload)

    assert resp["paymentId"] == "p-123"
    assert captured["method"] == "POST"
    # Validate idempotency header is set and is a UUID
    rid = captured["headers"].get("X-Request-ID")
    uuid.UUID(rid)

    # Metrics
    assert c_init.n == 1
    assert c_non2xx.n == 0
    assert h_lat.n == 1


# ---------------------------------------------------------------------------
# Payments: status non-2xx path
# ---------------------------------------------------------------------------

def test_payments_status_counts_non_2xx(monkeypatch):
    client = fin.FinastraAPIClient(token_provider=_fake_provider(), base_url="http://local")

    def fake_request(self, method, url, **_):
        return _DummyResp(status_code=502, url=url)

    monkeypatch.setattr(fin.requests.Session, "request", fake_request, raising=True)

    # Stub metrics
    class _C:
        def __init__(self):
            self.n = 0

        def labels(self, *_a, **_kw):
            return self

        def inc(self, v: int = 1):
            self.n += v
            return self

    class _H(_C):
        def observe(self, *_a, **_kw):
            self.inc(); return self

    c_status, c_non2xx, h_lat = _C(), _C(), _H()
    monkeypatch.setattr(fin, "_payments_status_total", c_status)
    monkeypatch.setattr(fin, "_non_2xx_total", c_non2xx)
    monkeypatch.setattr(fin, "_latency_hist", h_lat)

    with pytest.raises(Exception):
        client.payments_status("p-bad")

    assert c_status.n == 1
    assert c_non2xx.n == 1
    assert h_lat.n == 1


# ---------------------------------------------------------------------------
# Loans: happy path
# ---------------------------------------------------------------------------

def test_loans_get_success_and_latency(monkeypatch):
    client = fin.FinastraAPIClient(token_provider=_fake_provider(), base_url="http://local")

    def fake_request(self, method, url, **_):
        return _DummyResp(json_data={"id": "loan-1", "status": "ACTIVE"}, url=url)

    monkeypatch.setattr(fin.requests.Session, "request", fake_request, raising=True)

    class _C:
        def __init__(self):
            self.n = 0

        def labels(self, *_a, **_kw):
            return self

        def inc(self, v: int = 1):
            self.n += v
            return self

    class _H(_C):
        def observe(self, *_a, **_kw):
            self.inc(); return self

    c_loans, c_non2xx, h_lat = _C(), _C(), _H()
    monkeypatch.setattr(fin, "_loans_read_total", c_loans)
    monkeypatch.setattr(fin, "_non_2xx_total", c_non2xx)
    monkeypatch.setattr(fin, "_latency_hist", h_lat)

    data = client.loans_get("loan-1")

    assert data["id"] == "loan-1"
    assert c_loans.n == 1
    assert c_non2xx.n == 0
    assert h_lat.n == 1
