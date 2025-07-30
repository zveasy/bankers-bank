import httpx
import pytest
import respx
from starlette.testclient import TestClient

# Import the module itself (so we can patch its module-level constant)
import bank_connector.main as bc_main


@pytest.fixture(autouse=True)
def _patch_bank_api_url(monkeypatch):
    """
    Ensure the app posts to a predictable URL that we can mock with respx.
    This avoids relying on BANK_API_URL env or a live server.
    """
    monkeypatch.setattr(bc_main, "BANK_API_URL", "http://localhost:8000")


def test_post_sweep_order(respx_mock):
    # Mock the outbound call the app makes to the bank endpoint
    respx_mock.post("http://localhost:8000").mock(
        return_value=httpx.Response(200, text="<ok/>")
    )

    client = TestClient(bc_main.app)
    payload = {
        "order_id": "123",
        "amount": 10.0,
        "currency": "USD",
        "debtor": "Alice",
        "creditor": "Bob",
    }

    resp = client.post("/sweep-order", json=payload)
    assert resp.status_code == 200


def test_payment_status(respx_mock):
    # First call to the external bank endpoint during /sweep-order
    respx_mock.post("http://localhost:8000").mock(
        return_value=httpx.Response(200, text="<ok/>")
    )

    client = TestClient(bc_main.app)

    # Create a sweep order (this triggers the outbound POST we mocked above)
    client.post(
        "/sweep-order",
        json={"order_id": "abc", "amount": 1, "currency": "USD", "debtor": "A", "creditor": "B"},
    )

    # Now submit the bank's payment status callback
    xml = "<pain.002></pain.002>"
    resp = client.post("/payment-status", content=xml, headers={"X-Order-ID": "abc"})
    assert resp.status_code == 200
