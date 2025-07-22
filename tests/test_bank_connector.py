import json
import importlib.util
import pytest

HTTPX_AVAILABLE = importlib.util.find_spec("httpx") is not None
pytestmark = pytest.mark.skipif(not HTTPX_AVAILABLE, reason="httpx not installed")

if HTTPX_AVAILABLE:
    from fastapi.testclient import TestClient
    from bank_connector.main import app


def test_post_sweep_order(requests_mock):
    requests_mock.post("http://localhost:9999", text="<ok/>")
    client = TestClient(app)
    payload = {
        "order_id": "123",
        "amount": 10.0,
        "currency": "USD",
        "debtor": "Alice",
        "creditor": "Bob",
    }
    resp = client.post("/sweep-order", json=payload)
    assert resp.status_code == 200


def test_payment_status(requests_mock):
    xml = "<pain.002></pain.002>"
    requests_mock.post("http://localhost:9999", text="<ok/>")
    client = TestClient(app)
    client.post(
        "/sweep-order",
        json={"order_id": "abc", "amount": 1, "currency": "USD", "debtor": "A", "creditor": "B"},
    )
    resp = client.post("/payment-status", data=xml, headers={"X-Order-ID": "abc"})
    assert resp.status_code == 200
