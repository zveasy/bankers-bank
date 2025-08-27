from __future__ import annotations

"""Async client for Finastra balances endpoints.
Supports both per-account and list patterns; detects 404 path if unavailable.
"""

from typing import AsyncIterator, Dict, Optional

import httpx

from .http import FinastraHTTP
from .auth import TokenProvider

__all__ = ["Balance", "BalancesClient"]


class Balance(dict):
    """Typed alias for raw balance payload with parsed helpers."""

    @property
    def account_external_id(self) -> str:
        return self.get("accountId") or self.get("accountExternalId")

    @property
    def as_of_ts(self) -> str | None:  # ISO string
        return self.get("asOfDate") or self.get("updatedDate")


class BalancesClient:
    def __init__(
        self,
        http: Optional[FinastraHTTP] = None,
        *,
        base_url: Optional[str] = None,
        token_provider: Optional[TokenProvider] = None,
    ) -> None:
        self._own = http is None
        self.http = http or FinastraHTTP(
            base_url=base_url,
            token_provider=token_provider,
            product="balances",
        )

    async def __aenter__(self):
        await self.http.__aenter__()
        return self

    async def __aexit__(self, *exc):
        await self.http.__aexit__(*exc)
        if self._own:
            await self.http.aclose()

    # ------------------------------------------------------------------
    # Public helpers
    # ------------------------------------------------------------------

    async def balances_for_account(self, external_id: str) -> list[Balance]:
        """Return list (usually len 1) of balances for given account."""
        url = f"/corporate/channels/accounts/me/v1/accounts/{external_id}/balances"
        resp = await self.http.get(url)
        return [Balance(b) for b in resp.json().get("items", [])]

    async def list_all_balances(self, account_ids: list[str]) -> AsyncIterator[list[Balance]]:
        """Yield balance lists for each account (serially) to control rate."""
        for aid in account_ids:
            yield await self.balances_for_account(aid)
