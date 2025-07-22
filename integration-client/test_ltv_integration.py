import uuid
import importlib.util
import sys
from pathlib import Path
import pytest

from tests.test_helpers import REQUESTS_AVAILABLE
from test_helpers import clear_collateral_registry

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "sdk/python"))

from bankersbank.client import BankersBankClient

pytestmark = pytest.mark.skipif(not REQUESTS_AVAILABLE, reason="requests not installed")

@pytest.fixture(autouse=True)
def reset_collateral_registry():
    clear_collateral_registry()

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

@pytest.mark.skipif(not REQUESTS_AVAILABLE, reason="requests not installed")
def test_ltv_zero_collateral():
    client = BankersBankClient(base_url="http://127.0.0.1:8000", token="testtoken")
    # No collateral added for this test
    with pytest.raises(ValueError, match="Total collateral valuation is zero"):
        client.calculate_ltv("456783434")

@pytest.mark.skipif(not REQUESTS_AVAILABLE, reason="requests not installed")
def test_ltv_no_booked_balance():
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

@pytest.mark.skipif(not REQUESTS_AVAILABLE, reason="requests not installed")
def test_ltv_multiple_collateral():
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

@pytest.mark.skipif(not REQUESTS_AVAILABLE, reason="requests not installed")
def test_ltv_disputed_title():
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
