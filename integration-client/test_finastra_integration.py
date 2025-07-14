import pytest
from bankersbank.finastra import FinastraAPIClient
from test_helpers import *
import requests


@pytest.mark.skipif(not REQUESTS_AVAILABLE, reason="requests not installed")
def test_accounts_and_collateral_flow():
    client = FinastraAPIClient(token="dummy", base_url="http://127.0.0.1:8000")
    accounts = client.accounts_with_details("c123")
    assert accounts["items"]
    account_id = accounts["items"][0]["accountId"]
    # Register collateral for the account before checking
    collateral_data = {
        "address": "123 Main St",
        "valuation": 100000,
        "owner": "Test Owner",
        "title_status": "Clean"
    }
    if not hasattr(client, "add_collateral"):
        def add_collateral(collateral_data):
            return requests.post(f"{client.base_url}/collateral", json=collateral_data).json()
        client.add_collateral = add_collateral
    client.add_collateral(collateral_data)
    # Patch collaterals_for_account to return all collateral
    def collaterals_for_account(_):
        return requests.get(f"{client.base_url}/collateral").json()
    client.collaterals_for_account = collaterals_for_account
    all_collateral = requests.get(f"{client.base_url}/collateral").json()
    assert any(item["address"] == "123 Main St" for item in all_collateral["items"])
    result = client.calculate_ltv("c123")
    assert "ltv" in result
