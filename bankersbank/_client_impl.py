"""Canonical synchronous client implementation.
Extracted from bankersbank/client.py to avoid circular-import issues with SDK shim.
"""
from __future__ import annotations

from typing import Any, Dict, Optional

from .finastra import (
    FinastraAPIClient,
    ClientCredentialsTokenProvider,
    fetch_token,  # kept for convenience for legacy imports
)

# internal registry used by integration tests
_COLLATERAL_REGISTRY: dict[str, Any] = {}

__all__ = [
    "BankersBankClient",
    "FinastraAPIClient",
    "ClientCredentialsTokenProvider",
    "fetch_token",
    "_COLLATERAL_REGISTRY",
]

class BankersBankClient:
    """Backwards-compatible sync client that wraps the canonical FinastraAPIClient."""

    def __init__(
        self,
        token_or_provider: str | ClientCredentialsTokenProvider | None = None,
        *,
        token: str | None = None,
        base_url: Optional[str] = None,
        verify: bool | str = True,
    ) -> None:
        # legacy callers used keyword 'token='
        if token is not None and token_or_provider is None:
            token_or_provider = token
        if token_or_provider is None:
            raise ValueError("token_or_provider or token must be provided")
        self._client = FinastraAPIClient(
            token=token_or_provider,
            base_url=base_url,
            verify=verify,
        )

    # ---- Pass-through helpers -------------------------------------------------

    def accounts_with_details(self, consumer_id: str) -> Dict[str, Any]:
        return self._client.accounts_with_details(consumer_id)

    def get_collateral(self, collateral_id: str) -> Dict[str, Any]:
        return self._client.get_collateral(collateral_id)

    def list_collaterals(
        self,
        account_id: Optional[str] = None,
        page: int = 0,
        size: int = 50,
    ) -> Dict[str, Any]:
        return self._client.list_collaterals(account_id=account_id, page=page, size=size)

    def add_collateral(self, collateral_data: Dict[str, Any]) -> Dict[str, Any]:
        """Add collateral for testing purposes."""
        return self._client.add_collateral(collateral_data)

    def calculate_ltv(self, consumer_id: str) -> Dict[str, Any]:
        """Calculate LTV for a consumer."""
        return self._client.calculate_ltv(consumer_id)
