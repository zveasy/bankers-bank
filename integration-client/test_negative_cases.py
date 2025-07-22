import requests
import pytest
import importlib.util
import sys
from pathlib import Path

from tests.test_helpers import REQUESTS_AVAILABLE
from test_helpers import clear_collateral_registry

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "sdk/python"))

from bankersbank.client import BankersBankClient

pytestmark = pytest.mark.skipif(not REQUESTS_AVAILABLE, reason="requests not installed")

@pytest.fixture(autouse=True)
def _reset_registry():
    clear_collateral_registry()

@pytest.fixture
def client():
    return BankersBankClient(base_url="http://127.0.0.1:8000", token="testtoken")

def test_payment_blocked_recipient(client):
    with pytest.raises(requests.HTTPError) as exc:
        client.make_payment(
            debtor_id="456783434",
            creditor_name="Blocked Recipient",
            creditor_number="NL91 ABNA 0417 1643 00",
            amount=100.0,
            currency="USD",
            remittance="Blocked payment test"
        )
    assert exc.value.response.status_code == 403
    assert "blocked" in exc.value.response.text

def test_invalid_payment_amount(client):
    with pytest.raises(requests.HTTPError) as exc:
        client.make_payment(
            debtor_id="456783434",
            creditor_name="Jane Smith",
            creditor_number="NL91 ABNA 0417 1643 00",
            amount=0,  # Invalid amount
            currency="USD",
            remittance="Zero payment test"
        )
    assert exc.value.response.status_code == 400
    assert "Invalid amount" in exc.value.response.text

def test_account_not_found(client):
    with pytest.raises(requests.HTTPError) as exc:
        client.get_balances("NONEXISTENT_ID")
    assert exc.value.response.status_code == 404

def test_collateral_zero_valuation(client):
    bad_collateral = {
        "address": "300 Main St",
        "valuation": 0,
        "owner": "O&L Client A",
        "title_status": "Clean"
    }
    with pytest.raises(requests.HTTPError) as exc:
        client.add_collateral(bad_collateral)
    assert exc.value.response.status_code == 400
    assert "valuation" in exc.value.response.text.lower()

def test_collateral_missing_owner(client):
    bad_collateral = {
        "address": "400 Main St",
        "valuation": 400000,
        "title_status": "Clean"
    }
    with pytest.raises(requests.HTTPError) as exc:
        client.add_collateral(bad_collateral)
    assert exc.value.response.status_code == 400
    assert "owner" in exc.value.response.text

def test_collateral_duplicate_address(client):
    duplicate_collateral = {
        "address": "101 Market St",
        "valuation": 850000,
        "owner": "O&L Client A",
        "title_status": "Clean"
    }
    # First one should succeed
    client.add_collateral(duplicate_collateral)
    # Second one should fail
    with pytest.raises(requests.HTTPError) as exc:
        client.add_collateral(duplicate_collateral)
    assert exc.value.response.status_code == 409
    assert "already registered" in exc.value.response.text
