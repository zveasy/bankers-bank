import json
import pytest
from fastapi.testclient import TestClient

from bank_connector.main import app



@pytest.mark.enable_socket
def test_post_sweep_order(requests_mock):
    requests_mock.post("http://localhost:8000", text="<ok/>")
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


@pytest.mark.enable_socket
def test_payment_status(requests_mock):
    xml = "<pain.002></pain.002>"
    requests_mock.post("http://localhost:8000", text="<ok/>")
    client = TestClient(app)
import pytest
from fastapi.testclient import TestClient

from bank_connector.main import app

@pytest.mark.enable_socket
def test_post_sweep_order():
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

@pytest.mark.enable_socket
def test_payment_status():
    xml = "<pain.002></pain.002>"
    client = TestClient(app)
    client.post(
        "/sweep-order",
        json={"order_id": "abc", "amount": 1, "currency": "USD", "debtor": "A", "creditor": "B"},
    )
    resp = client.post("/payment-status", data=xml, headers={"X-Order-ID": "abc"})
    assert resp.status_code == 200
