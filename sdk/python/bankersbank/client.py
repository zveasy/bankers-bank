import requests
import os
from typing import Dict, Any

def _use_mock() -> bool:
    """
    Returns True if we should call the local mock server
    instead of the live Finastra Accounts & Balances API.
    """
    return os.getenv("USE_MOCK_BALANCES", "true").lower() in ("1", "true", "yes")
class BankersBankClient:
    def __init__(self, base_url, token=None):
        self.base_url = base_url.rstrip("/")
        self.token = token

    def _headers(self):
        headers = {"Content-Type": "application/json"}
        if self.token:
            headers["Authorization"] = f"Bearer {self.token}"
        return headers

    def list_accounts(self, account_context: str = "VIEW-ACCOUNT") -> Dict[str, Any]:
            if _use_mock():
                url = f"{self.base_url}/corporate/channels/accounts/me/v1/accounts"
            else:
                # Live Finastra URL
                url = (
                    "https://api.fusionfabric.cloud/"
                    "corporate/channels/accounts/me/v1/accounts"
                )
            params = {"accountContext": account_context}
            resp = requests.get(url, params=params, headers=self._headers())
            print("Status:", resp.status_code)
            print("Content:", resp.text)
            resp.raise_for_status()
            return resp.json()

    def get_balances(self, account_id: str) -> Dict[str, Any]:
        if _use_mock():
            url = (
                f"{self.base_url}/corporate/channels/accounts/me/v1/"
                f"accounts/{account_id}/balances"
            )
        else:
            url = (
                f"https://api.fusionfabric.cloud/corporate/channels/accounts/"
                f"me/v1/accounts/{account_id}/balances"
            )
        resp = requests.get(url, headers=self._headers())
        print("Status:", resp.status_code)
        print("Content:", resp.text)
        resp.raise_for_status()
        return resp.json()

    def get_transactions(self, account_id):
        url = f"{self.base_url}/corporate/channels/accounts/me/v1/accounts/{account_id}/transactions"
        resp = requests.get(url, headers=self._headers())
        resp.raise_for_status()
        return resp.json()

    def make_payment(self, debtor_id, creditor_name, creditor_number, amount, currency, remittance):
        url = f"{self.base_url}/corporate/channels/accounts/me/v1/payments"
        body = {
            "debtorAccount": {"id": debtor_id},
            "creditorAccount": {"name": creditor_name, "number": creditor_number},
            "amount": amount,
            "currency": currency,
            "remittanceInformation": remittance
        }
        resp = requests.post(url, json=body, headers=self._headers())
        resp.raise_for_status()
        return resp.json()
    
    def add_collateral(self, collateral_data):
        url = f"{self.base_url}/collateral"
        resp = requests.post(url, json=collateral_data, headers=self._headers())
        print(f"Status: {resp.status_code}")
        print(f"Content: {resp.text}")
        resp.raise_for_status()
        return resp.json()

    def get_collateral(self):
        url = f"{self.base_url}/collateral"
        resp = requests.get(url, headers=self._headers())
        print(f"Status: {resp.status_code}")
        print(f"Content: {resp.text}")
        resp.raise_for_status()
        return resp.json()

    def calculate_ltv(self, account_id: str) -> Dict[str, Any]:
        """Calculate loan-to-value for an account.

        This helper fetches the account's booked balance and the list of
        registered collateral from the mock API, returning the computed LTV
        ratio along with the raw values.
        """
        balances = self.get_balances(account_id)
        booked = next(
            (b for b in balances.get("items", []) if b.get("type") == "BOOKED"),
            None,
        )
        if not booked:
            raise ValueError("BOOKED balance not found for account")

        loan_balance = float(booked.get("amount", 0))

        collateral_resp = self.get_collateral()
        total_collateral = sum(
            float(c.get("valuation", 0)) for c in collateral_resp.get("items", [])
        )
        if total_collateral == 0:
            raise ValueError("Total collateral valuation is zero")

        ltv = loan_balance / total_collateral
        return {
            "account_id": account_id,
            "loan_balance": loan_balance,
            "total_collateral": total_collateral,
            "ltv": ltv,
        }
