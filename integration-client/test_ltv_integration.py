import uuid
import pytest

from conftest import REQUESTS_AVAILABLE

from bankersbank.client import BankersBankClient

@pytest.mark.skipif(not REQUESTS_AVAILABLE, reason="requests not installed")
def test_calculate_ltv_integration():
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
