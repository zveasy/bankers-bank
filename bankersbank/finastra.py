"""Stub Finastra API client for legacy tests."""
from typing import Dict, List
import requests

TOKEN_URL = "https://api.fusionfabric.cloud/login/v1/sandbox/oidc/token"  # Finastra sandbox token endpoint



def fetch_token(client_id: str, client_secret: str) -> str:
    """Retrieve an OAuth2 token from Finastra FFDC.

    Parameters
    ----------
    client_id: str
        OAuth2 client ID issued by Finastra.
    client_secret: str
        OAuth2 client secret issued by Finastra.

    Returns
    -------
    str
        Access token string.
    """
    data = {
        "grant_type": "client_credentials",
        "client_id": client_id,
        "client_secret": client_secret,
        "scope": "FFDC"  # default FFDC scope
    }
    resp = requests.post(TOKEN_URL, data=data, timeout=10)
    resp.raise_for_status()
    token = resp.json().get("access_token")
    if not token:
        raise RuntimeError("Failed to obtain access_token from Finastra response")
    return token


class FinastraAPIClient:
    def __init__(self, token: str):
        self.token = token

    def collaterals_for_account(self, account_id: str) -> Dict[str, List[Dict]]:  # type: ignore[override]
        """Return dummy collateral data; tests monkeypatch this method."""
        return {"items": []}
