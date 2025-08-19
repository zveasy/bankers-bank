import os
import uuid
from typing import Any, Dict

import requests

TOKEN_URL = "https://api.fusionfabric.cloud/login/v1/sandbox/oidc/token"


def fetch_token(client_id: str, client_secret: str, scope: str = "accounts") -> str:
    """Fetch OAuth2 token using client credentials."""
    headers = {"Content-Type": "application/x-www-form-urlencoded"}
    data = {
        "grant_type": "client_credentials",
        "client_id": client_id,
        "client_secret": client_secret,
        "scope": scope,
    }
    resp = requests.post(TOKEN_URL, headers=headers, data=data)
    resp.raise_for_status()
    return resp.json()["access_token"]


def _use_mock() -> bool:
    return os.getenv("USE_MOCK_BALANCES", "true").lower() in ("1", "true", "yes")


class FinastraAPIClient:
    """Minimal client for Finastra Account & Collateral APIs."""

    def __init__(self, token: str, base_url: str = "https://127.0.0.1:8000", verify: str | bool = True):
        self.token = token
        self.base_url = base_url.rstrip("/")
        self.verify = verify

    def _headers(self) -> Dict[str, str]:
        return {
            "Authorization": f"Bearer {self.token}",
            "X-Request-ID": str(uuid.uuid4()),
            "Content-Type": "application/json",
        }

    def accounts_with_details(self, consumer_id: str) -> Dict[str, Any]:
        if _use_mock():
            url = (
                f"{self.base_url}/consumers/{consumer_id}/accounts/extendedWithDetails"
            )
        else:
            url = (
                "https://api.fusionfabric.cloud/account-information/v2/consumers/"
                f"{consumer_id}/accounts/extendedWithDetails"
            )
        kwargs = {"verify": self.verify} if self.verify is not True else {}
        resp = requests.get(url, headers=self._headers(), **kwargs)
        resp.raise_for_status()
        return resp.json()

    def collaterals_for_account(self, account_id: str) -> Dict[str, Any]:
        if _use_mock():
            url = f"{self.base_url}/collaterals"
            params = {"accountId": account_id}
        else:
            url = "https://api.fusionfabric.cloud/collateral/v1/collaterals"
            params = {"accountId": account_id}
        kwargs = {"verify": self.verify} if self.verify is not True else {}
        resp = requests.get(url, params=params, headers=self._headers(), **kwargs)
        resp.raise_for_status()
        return resp.json()

    def calculate_ltv(self, consumer_id: str) -> Dict[str, Any]:
        accounts = self.accounts_with_details(consumer_id)
        if not accounts.get("items"):
            raise ValueError("No accounts found for consumer")
        account = accounts["items"][0]
        account_id = account["accountId"]
        booked = next(
            (b for b in account.get("balances", []) if b.get("type") == "BOOKED"), None
        )
        if not booked:
            raise ValueError("BOOKED balance not found")
        loan_balance = float(booked["amount"])
        collateral_resp = self.collaterals_for_account(account_id)
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
