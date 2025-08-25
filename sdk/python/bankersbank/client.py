import os
from typing import Any, Dict

import requests

try:
    # Reuse the mock API's collateral registry when available
    from mocks.mock_finastra_api import \
        collateral_registry as _COLLATERAL_REGISTRY
except Exception:  # pragma: no cover - fallback for production envs
    _COLLATERAL_REGISTRY: list[dict] = []


def _use_mock() -> bool:
    """
    Returns True if we should call the local mock server
    instead of the live Finastra Accounts & Balances API.
    """
    return os.getenv("USE_MOCK_BALANCES", "true").lower() in ("1", "true", "yes")


class BankersBankClient:
    def __init__(self, base_url, token=None, verify: str | bool = True):
        self.base_url = base_url.rstrip("/")
        self.token = token
        self.verify = verify

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
        kwargs = {"verify": self.verify} if self.verify is not True else {}
        resp = requests.get(url, params=params, headers=self._headers(), **kwargs)
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
        kwargs = {"verify": self.verify} if self.verify is not True else {}
        resp = requests.get(url, headers=self._headers(), **kwargs)
        print("Status:", resp.status_code)
        print("Content:", resp.text)
        resp.raise_for_status()
        return resp.json()

    def get_transactions(self, account_id):
        url = f"{self.base_url}/corporate/channels/accounts/me/v1/accounts/{account_id}/transactions"
        kwargs = {"verify": self.verify} if self.verify is not True else {}
        resp = requests.get(url, headers=self._headers(), **kwargs)
        resp.raise_for_status()
        return resp.json()

    def make_payment(
        self, debtor_id, creditor_name, creditor_number, amount, currency, remittance
    ):
        url = f"{self.base_url}/corporate/channels/accounts/me/v1/payments"
        body = {
            "debtorAccount": {"id": debtor_id},
            "creditorAccount": {"name": creditor_name, "number": creditor_number},
            "amount": amount,
            "currency": currency,
            "remittanceInformation": remittance,
        }
        kwargs = {"verify": self.verify} if self.verify is not True else {}
        resp = requests.post(url, json=body, headers=self._headers(), **kwargs)
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
        """Calculate loan-to-value for an account using the mock API's /ltv/calculate endpoint."""
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

        # Call the mock API's /ltv/calculate endpoint
        url = f"{self.base_url}/ltv/calculate"
        resp = requests.post(
            url,
            json={"collateral_value": total_collateral, "loan_amount": loan_balance},
            headers=self._headers(),
        )
        resp.raise_for_status()
        ltv_result = resp.json()
        return {
            "account_id": account_id,
            "loan_balance": loan_balance,
            "total_collateral": total_collateral,
            **ltv_result,
        }
