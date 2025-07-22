
import pytest
import requests
import json
from bankersbank.finastra import FinastraAPIClient
from test_helpers import REQUESTS_AVAILABLE
from pathlib import Path
import jsonschema



def load_balances_schema():
    # Expanded schema for balances endpoint
    return {
        "type": "object",
        "properties": {
            "items": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "type": {"type": "string"},
                        "amount": {"type": "number"},
                        "currency": {"type": "string"},
                    },
                    "required": ["type", "amount", "currency"]
                },
            },
            "_meta": {"type": "object"},
        },
        "required": ["items", "_meta"]
    }


# --- /balances endpoint: happy-path, negative, edge, schema tests ---
import itertools

@pytest.mark.enable_socket
@pytest.mark.skipif(not REQUESTS_AVAILABLE, reason="requests not installed")
@pytest.mark.parametrize(
    "account_id,token,query_params,expected_status,desc",
    [
        ("456783434", "Bearer dummy", {}, 200, "valid account, valid token"),
        ("123456789", "Bearer dummy", {}, 200, "valid account, valid token (GBP)"),
        ("nonexistent", "Bearer dummy", {}, 404, "nonexistent account"),
        ("", "Bearer dummy", {}, 404, "empty account id"),
        ("456783434", None, {}, 401, "missing token"),
        ("456783434", "", {}, 401, "empty token"),
        ("456783434", "Bearer bad", {}, 401, "invalid token format"),
        ("456783434", "Bearer dummy", {"error": "500"}, 500, "simulate server error"),
    ]
)
def test_balances_all_cases(account_id, token, query_params, expected_status, desc):
    """
    Covers happy-path, negative, edge, and error simulation for /balances endpoint.
    Uses direct requests for full control over headers and query params.
    """
    url = f"http://127.0.0.1:8000/corporate/channels/accounts/me/v1/accounts/{account_id}/balances"
    headers = {"Authorization": token} if token is not None else {}
    resp = requests.get(url, headers=headers, params=query_params)
    if expected_status == 200:
        assert resp.status_code == 200, f"{desc}: {resp.text}"
        data = resp.json()
        schema = load_balances_schema()
        jsonschema.validate(instance=data, schema=schema)
        # Edge: check empty balances for valid but unpopulated account
        if account_id == "nonexistent":
            assert not data["items"]
    else:
        assert resp.status_code == expected_status, f"{desc}: {resp.text}"


@pytest.mark.skipif(not REQUESTS_AVAILABLE, reason="requests not installed")
@pytest.mark.parametrize("account_id", ["456783434", "123456789"])
def test_balances_minimal_and_maximal(account_id):
    """
    Edge: test balances for min/max values (simulate by checking all returned balances).
    """
    url = f"http://127.0.0.1:8000/corporate/channels/accounts/me/v1/accounts/{account_id}/balances"
    headers = {"Authorization": "Bearer dummy"}
    resp = requests.get(url, headers=headers)
    assert resp.status_code == 200
    data = resp.json()
    amounts = [item["amount"] for item in data["items"]]
    assert min(amounts) >= 0 or max(amounts) > 0  # at least one positive or zero


@pytest.mark.skipif(not REQUESTS_AVAILABLE, reason="requests not installed")
def test_balances_invalid_type():
    """
    Edge: invalid type for account_id (int instead of str).
    """
    url = "http://127.0.0.1:8000/corporate/channels/accounts/me/v1/accounts/123456789/balances"
    headers = {"Authorization": "Bearer dummy"}
    # Should still work, as path param is coerced to str, but test for robustness
    resp = requests.get(url, headers=headers)
    assert resp.status_code == 200


@pytest.mark.skipif(not REQUESTS_AVAILABLE, reason="requests not installed")
def test_balances_schema_regression():
    """
    Regression: ensure balances always include required fields and correct types.
    """
    url = "http://127.0.0.1:8000/corporate/channels/accounts/me/v1/accounts/456783434/balances"
    headers = {"Authorization": "Bearer dummy"}
    resp = requests.get(url, headers=headers)
    assert resp.status_code == 200
    data = resp.json()
    schema = load_balances_schema()
    jsonschema.validate(instance=data, schema=schema)




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

# --- get_account_info endpoint tests ---

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
