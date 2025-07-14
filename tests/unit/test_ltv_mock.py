import pytest
import os
from sdk.python.bankersbank.client import BankersBankClient
import requests

def reset_collateral(base_url):
    # Reset the in-memory collateral registry for test isolation
    resp = requests.post(f"{base_url}/collateral/reset")
    assert resp.status_code == 200

def setup_collateral_and_account(client, account_id, address="123 Main St", valuation=100000):
    # Add collateral
    collateral_data = {
        "address": address,
        "valuation": valuation,
        "owner": "Alice",
        "title_status": "clear"
    }
    client.add_collateral(collateral_data)
    # No need to create account, just ensure balance exists in mock


def test_calculate_ltv_against_mock(monkeypatch):
    os.environ["USE_MOCK_BALANCES"] = "true"
    base_url = "http://localhost:8000"
    reset_collateral(base_url)
    client = BankersBankClient(base_url)
    account_id = "456783434"  # This is in SAMPLE_ACCOUNTS and SAMPLE_BALANCES
    setup_collateral_and_account(client, account_id)
    result = client.calculate_ltv(account_id)
    assert "ltv" in result
    assert result["ltv"] == 10500.0 / 100000
    assert result["loan_balance"] == 10500.0
    assert result["total_collateral"] == 100000


def test_ltv_zero_collateral(monkeypatch):
    os.environ["USE_MOCK_BALANCES"] = "true"
    base_url = "http://localhost:8000"
    reset_collateral(base_url)
    client = BankersBankClient(base_url)
    account_id = "456783434"
    # Do not add collateral
    with pytest.raises(ValueError, match="Total collateral valuation is zero"):
        client.calculate_ltv(account_id)


def test_ltv_multiple_collateral(monkeypatch):
    os.environ["USE_MOCK_BALANCES"] = "true"
    base_url = "http://localhost:8000"
    reset_collateral(base_url)
    client = BankersBankClient(base_url)
    account_id = "456783434"
    setup_collateral_and_account(client, account_id, address="1 A St", valuation=100000)
    setup_collateral_and_account(client, account_id, address="2 B St", valuation=50000)
    result = client.calculate_ltv(account_id)
    assert result["total_collateral"] == 150000
    assert result["ltv"] == 10500.0 / 150000


def test_ltv_no_booked_balance(monkeypatch):
    os.environ["USE_MOCK_BALANCES"] = "true"
    base_url = "http://localhost:8000"
    reset_collateral(base_url)
    client = BankersBankClient(base_url)
    # Use a non-existent account id
    account_id = "999999999"
    setup_collateral_and_account(client, account_id)
    with pytest.raises(requests.HTTPError):
        client.calculate_ltv(account_id)
