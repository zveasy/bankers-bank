from tests.test_helpers import *
import sys
from pathlib import Path
import pytest
import uuid

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "sdk/python"))

from bankersbank.client import BankersBankClient

pytestmark = pytest.mark.skipif(
    not REQUESTS_AVAILABLE, reason="requests not installed"
)

client = BankersBankClient(base_url="http://127.0.0.1:8000", token="testtoken")


@pytest.fixture(autouse=True)
def reset_collateral_registry():
    clear_collateral_registry()


def test_list_accounts():
    accounts = client.list_accounts()
    assert isinstance(accounts, dict)
    assert "items" in accounts
    assert len(accounts["items"]) > 0
    global account_id  # For use in dependent tests (optional)
    account_id = accounts['items'][0]['id']


def test_get_balances():
    accounts = client.list_accounts()
    account_id = accounts['items'][0]['id']
    balances = client.get_balances(account_id)
    assert isinstance(balances, dict)
    assert "items" in balances
    assert len(balances["items"]) > 0


def test_get_transactions():
    accounts = client.list_accounts()
    account_id = accounts['items'][0]['id']
    transactions = client.get_transactions(account_id)
    assert isinstance(transactions, dict)
    assert "items" in transactions


def test_make_payment():
    accounts = client.list_accounts()
    account_id = accounts['items'][0]['id']
    payment = client.make_payment(
        debtor_id=account_id,
        creditor_name="Jane Smith",
        creditor_number="NL91 ABNA 0417 1643 00",
        amount=200.0,
        currency="USD",
        remittance="Invoice #12345"
    )
    assert isinstance(payment, dict)
    assert payment.get("status") == "CONFIRMED"


def test_add_and_get_collateral():
    collateral = {
        "address": f"101 Market St {uuid.uuid4()}",
        "valuation": 850000,
        "owner": "O&L Client A",
        "title_status": "Clean"
    }
    add_collateral_resp = client.add_collateral(collateral)
    assert isinstance(add_collateral_resp, dict)
    assert add_collateral_resp.get("status") == "REGISTERED"

    get_collateral_resp = client.get_collateral()
    assert isinstance(get_collateral_resp, dict)
    assert "items" in get_collateral_resp
    assert any(item["address"] == collateral["address"] for item in get_collateral_resp["items"])
