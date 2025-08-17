"""Stub Finastra API client for legacy tests."""
from typing import Dict, List

class FinastraAPIClient:
    def __init__(self, token: str):
        self.token = token

    def collaterals_for_account(self, account_id: str) -> Dict[str, List[Dict]]:  # type: ignore[override]
        """Return dummy collateral data; tests monkeypatch this method."""
        return {"items": []}
