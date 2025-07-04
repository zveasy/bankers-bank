from conftest import REQUESTS_AVAILABLE
from bankersbank.client import BankersBankClient
import requests
import pytest

pytestmark = pytest.mark.skipif(
    not REQUESTS_AVAILABLE, reason="requests not installed"
)

client = BankersBankClient(base_url="http://127.0.0.1:8000", token="testtoken")

try:
    accounts = client.list_accounts()
    print("Accounts:", accounts)
    account_id = accounts['items'][0]['id']
except Exception as e:
    print("Error listing accounts:", e)
    account_id = None

if account_id:
    try:
        balances = client.get_balances(account_id)
        print("Balances:", balances)
    except Exception as e:
        print("Error getting balances:", e)

    try:
        transactions = client.get_transactions(account_id)
        print("Transactions:", transactions)
    except Exception as e:
        print("Error getting transactions:", e)

    try:
        payment = client.make_payment(
            debtor_id=account_id,
            creditor_name="Jane Smith",
            creditor_number="NL91 ABNA 0417 1643 00",
            amount=200.0,
            currency="USD",
            remittance="Invoice #12345"
        )
        print("Payment:", payment)
    except Exception as e:
        print("Error initiating payment:", e)

    try:
        collateral = {
            "address": "101 Market St",
            "valuation": 850000,
            "owner": "O&L Client A",
            "title_status": "Clean"
        }
        add_collateral_resp = client.add_collateral(collateral)
        print("Add Collateral:", add_collateral_resp)
    except Exception as e:
        print("Error adding collateral:", e)

    try:
        get_collateral_resp = client.get_collateral()
        print("Get Collateral:", get_collateral_resp)
    except Exception as e:
        print("Error getting collateral:", e)
