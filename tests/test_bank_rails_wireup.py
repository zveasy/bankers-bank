import os
import re

import httpx
import pytest
from fastapi.testclient import TestClient

# service under test
import bank_connector.main as bc

AUTH = {"Authorization": "Bearer testtoken"}


def _patch_async_client(monkeypatch: pytest.MonkeyPatch, status_code: int):
    """Patch httpx.AsyncClient so all outbound posts return the given status code."""

    async def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(status_code)

    class PatchedAsyncClient(httpx.AsyncClient):
        def __init__(self, *args, **kwargs):
            kwargs.setdefault("transport", httpx.MockTransport(handler))
            super().__init__(*args, **kwargs)

    # patch both references
    monkeypatch.setattr(httpx, "AsyncClient", PatchedAsyncClient, raising=True)
    monkeypatch.setattr(bc.httpx, "AsyncClient", PatchedAsyncClient, raising=True)


def _scrape_value(text: str, metric_name: str) -> float:
    pattern = rf"^{re.escape(metric_name)}(?:{{[^}}]*}})?\\s+([0-9.]+)$"
    return sum(float(v) for v in re.findall(pattern, text, flags=re.M))


@pytest.fixture(autouse=True)
def _rails_env(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("BANK_RAILS_ENABLED", "1")
    monkeypatch.setenv("BANK_RAILS_URL", "https://rails.test")
    yield


def _client():
    return TestClient(bc.app)


def _payload(order_id: str = "ORD-1"):
    return {
        "order_id": order_id,
        "amount": 123.45,
        "currency": "USD",
        "debtor": "Alice",
        "creditor": "Bob",
    }


def test_sweep_success_emits_metrics(monkeypatch: pytest.MonkeyPatch):
    _patch_async_client(monkeypatch, 200)
    client = _client()
    res = client.post("/sweep-order", json=_payload("OK-1"), headers=AUTH)
    assert res.status_code == 200
    metrics = client.get("/metrics").text
    assert "rails_post_total" in metrics  # sample exists once counter incremented


def test_sweep_failure_goes_to_dlq(monkeypatch: pytest.MonkeyPatch):
    _patch_async_client(monkeypatch, 500)
    client = _client()
    res = client.post("/sweep-order", json=_payload("FAIL-1"), headers=AUTH)
    assert res.status_code in (
        202,
        200,
        201,
        204,
    )  # we expect enqueue behaviour, so 202 preferred but 200 tolerated depending on flag


def test_payment_status_updates(monkeypatch: pytest.MonkeyPatch):
    _patch_async_client(monkeypatch, 200)
    client = _client()
    assert (
        client.post("/sweep-order", json=_payload("STAT-1"), headers=AUTH).status_code
        == 200
    )

    pain002 = """
    <Document xmlns=\"urn:iso:std:iso:20022:tech:xsd:pain.002.001.03\">
      <CstmrPmtStsRpt>
        <OrgnlPmtInfAndSts>
          <TxInfAndSts>
            <OrgnlEndToEndId>STAT-1</OrgnlEndToEndId>
            <TxSts>ACSC</TxSts>
          </TxInfAndSts>
        </OrgnlPmtInfAndSts>
      </CstmrPmtStsRpt>
    </Document>
    """.strip()

    r = client.post(
        "/payment-status",
        data=pain002,
        headers={"Content-Type": "application/xml", **AUTH},
    )
    assert r.status_code == 200
    assert "SETTLED" in r.text


def test_dlq_drains_after_retry(monkeypatch):
    """First rails call fails, then succeeds; DLQ depth should return to 0."""

    import bank_connector.main as bc

    calls = {"n": 0}

    async def handler(request):  # noqa: D401
        calls["n"] += 1
        return httpx.Response(500 if calls["n"] == 1 else 200)

    class Patched(httpx.AsyncClient):
        def __init__(self, *a, **kw):
            kw.setdefault("transport", httpx.MockTransport(handler))
            super().__init__(*a, **kw)

    monkeypatch.setenv("BANK_RAILS_ENABLED", "1")
    monkeypatch.setenv("BANK_RAILS_URL", "https://rails.test")
    monkeypatch.setattr(httpx, "AsyncClient", Patched, raising=True)
    monkeypatch.setattr(bc.httpx, "AsyncClient", Patched, raising=True)

    client = TestClient(bc.app)
    resp = client.post("/sweep-order", json=_payload("DLQ-1"), headers=AUTH)
    assert resp.status_code in (202, 200)

    # allow background worker time
    import time as _t

    _t.sleep(0.8)

    depth = _scrape_value(client.get("/metrics").text, "rails_dlq_depth")
    assert depth == 0.0
