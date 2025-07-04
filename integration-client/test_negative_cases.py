from conftest import REQUESTS_AVAILABLE
from bankersbank.client import BankersBankClient
import requests
import pytest

pytestmark = pytest.mark.skipif(
    not REQUESTS_AVAILABLE, reason="requests not installed"
)

client = BankersBankClient(base_url="http://127.0.0.1:8000", token="testtoken")

def test_payment_blocked_recipient():
    try:
        # Should trigger 403 error
        resp = client.make_payment(
            debtor_id="456783434",
            creditor_name="Blocked Recipient",
            creditor_number="NL91 ABNA 0417 1643 00",
            amount=100.0,
            currency="USD",
            remittance="Blocked payment test"
        )
        print("UNEXPECTED SUCCESS (blocked recipient):", resp)
    except requests.HTTPError as e:
        print("Expected 403 error caught (blocked recipient):", e.response.status_code, e.response.text)

def test_invalid_payment_amount():
    try:
        # Should trigger 400 error
        resp = client.make_payment(
            debtor_id="456783434",
            creditor_name="Jane Smith",
            creditor_number="NL91 ABNA 0417 1643 00",
            amount=0,  # Invalid amount
            currency="USD",
            remittance="Zero payment test"
        )
        print("UNEXPECTED SUCCESS (invalid amount):", resp)
    except requests.HTTPError as e:
        print("Expected 400 error caught (invalid amount):", e.response.status_code, e.response.text)

def test_account_not_found():
    try:
        # Should trigger 404 error
        resp = client.get_balances("NONEXISTENT_ID")
        print("UNEXPECTED SUCCESS (account not found):", resp)
    except requests.HTTPError as e:
        print("Expected 404 error caught (account not found):", e.response.status_code, e.response.text)

def test_collateral_zero_valuation():
    try:
        # Edge Case: Zero Valuation
        bad_collateral = {
            "address": "300 Main St",
            "valuation": 0,
            "owner": "O&L Client A",
            "title_status": "Clean"
        }
        client.add_collateral(bad_collateral)
        print("UNEXPECTED SUCCESS (zero valuation collateral)")
    except Exception as e:
        print("Expected error for zero valuation:", e)

def test_collateral_missing_owner():
    try:
        # Edge Case: Missing owner
        bad_collateral = {
            "address": "400 Main St",
            "valuation": 400000,
            "title_status": "Clean"
        }
        client.add_collateral(bad_collateral)
        print("UNEXPECTED SUCCESS (missing owner in collateral)")
    except Exception as e:
        print("Expected error for missing owner:", e)

def test_collateral_duplicate_address():
    try:
        # Edge Case: Duplicate address
        duplicate_collateral = {
            "address": "101 Market St",
            "valuation": 850000,
            "owner": "O&L Client A",
            "title_status": "Clean"
        }
        client.add_collateral(duplicate_collateral)
        client.add_collateral(duplicate_collateral)  # 2nd time should fail
        print("UNEXPECTED SUCCESS (duplicate collateral)")
    except Exception as e:
        print("Expected error for duplicate collateral:", e)

if __name__ == "__main__":
    test_payment_blocked_recipient()
    test_invalid_payment_amount()
    test_account_not_found()
    test_collateral_zero_valuation()
    test_collateral_missing_owner()
    test_collateral_duplicate_address()