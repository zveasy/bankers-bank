import pytest
from bankersbank.finastra import FinastraAPIClient
from conftest import REQUESTS_AVAILABLE


@pytest.mark.skipif(not REQUESTS_AVAILABLE, reason="requests not installed")
def test_accounts_and_collateral_flow():
    client = FinastraAPIClient(token="dummy", base_url="http://127.0.0.1:8000")
    accounts = client.accounts_with_details("c123")
    assert accounts["items"]
    account_id = accounts["items"][0]["accountId"]
    collateral = client.collaterals_for_account(account_id)
    assert collateral["items"]
    result = client.calculate_ltv("c123")
    assert "ltv" in result
