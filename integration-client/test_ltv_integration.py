import uuid
import pytest
import requests

from conftest import REQUESTS_AVAILABLE

from bankersbank.client import BankersBankClient

def clear_collateral_registry():
    # Remove all collateral from the mock server for test isolation
    resp = requests.get("http://127.0.0.1:8000/collateral")
    for item in resp.json().get("items", []):
        # No delete endpoint, so we clear by restarting server or using unique addresses
        pass

@pytest.mark.skipif(not REQUESTS_AVAILABLE, reason="requests not installed")
def test_calculate_ltv_integration():
    clear_collateral_registry()
    client = BankersBankClient(base_url="http://127.0.0.1:8000", token="testtoken")

    collateral = {
        "address": str(uuid.uuid4()),
        "valuation": 100000,
        "owner": "O&L Client A",
        "title_status": "Clean",
    }
    client.add_collateral(collateral)
    result = client.calculate_ltv("456783434")
    assert pytest.approx(result["ltv"]) == 10500.0 / 100000.0

def test_ltv_zero_collateral():
    clear_collateral_registry()
    client = BankersBankClient(base_url="http://127.0.0.1:8000", token="testtoken")
    # No collateral added for this test
    with pytest.raises(ValueError, match="Total collateral valuation is zero"):
        client.calculate_ltv("456783434")

def test_ltv_no_booked_balance():
    clear_collateral_registry()
    client = BankersBankClient(base_url="http://127.0.0.1:8000", token="testtoken")
    # Add collateral so that only balance is missing
    collateral = {
        "address": str(uuid.uuid4()),
        "valuation": 100000,
        "owner": "O&L Client B",
        "title_status": "Clean",
    }
    client.add_collateral(collateral)
    # Use a non-existent account id
    with pytest.raises(requests.HTTPError) as exc:
        client.calculate_ltv("nonexistent")
    assert exc.value.response.status_code == 404

def test_ltv_multiple_collateral():
    clear_collateral_registry()
    client = BankersBankClient(base_url="http://127.0.0.1:8000", token="testtoken")
    collateral1 = {
        "address": str(uuid.uuid4()),
        "valuation": 100000,
        "owner": "O&L Client C",
        "title_status": "Clean",
    }
    collateral2 = {
        "address": str(uuid.uuid4()),
        "valuation": 50000,
        "owner": "O&L Client D",
        "title_status": "Clean",
    }
    client.add_collateral(collateral1)
    client.add_collateral(collateral2)
    result = client.calculate_ltv("456783434")
    assert result["total_collateral"] == 150000
    assert pytest.approx(result["ltv"]) == 10500.0 / 150000.0

def test_ltv_disputed_title():
    clear_collateral_registry()
    client = BankersBankClient(base_url="http://127.0.0.1:8000", token="testtoken")
    disputed_collateral = {
        "address": str(uuid.uuid4()),
        "valuation": 100000,
        "owner": "O&L Client E",
        "title_status": "disputed",
    }
    with pytest.raises(requests.HTTPError) as exc:
        client.add_collateral(disputed_collateral)
    assert exc.value.response.status_code == 403
    assert "disputed" in exc.value.response.text
