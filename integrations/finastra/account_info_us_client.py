from __future__ import annotations
"""Async client for Finastra *Account Information (US)* product.

Implements only the endpoints we need for batch transaction sync:
1. `GET /corporate/channels/accounts/me/v1/accounts/{accountId}/transactions` – paginated list
2. `GET /corporate/channels/accounts/me/v1/accounts/{accountId}` – account details (optional convenience)

The Finastra pagination scheme uses `_meta.pageCount`. This client mirrors the pattern
already used in `AccountsClient` and is designed to be MockTransport-friendly so offline
unit tests can provide deterministic responses.
"""

import asyncio
from dataclasses import dataclass
from datetime import datetime
from typing import AsyncIterator, Dict, List, Optional

import httpx

from .auth import TokenProvider
from .http import FinastraHTTP

__all__ = ["Transaction", "AccountInfoUSClient"]


@dataclass(slots=True)
class Transaction:
    """DTO representing a single account transaction record."""

    external_tx_id: str
    account_external_id: str
    raw: Dict

    # parsed convenience fields (optional)
    amount: Optional[str] = None  # keep as string for precise Decimal later
    currency: Optional[str] = None
    booking_date: Optional[str] = None  # ISO string
    description: Optional[str] = None
    reference: Optional[str] = None
    direction: Optional[str] = None  # "CR" or "DR"
    status: Optional[str] = None
    scheme: Optional[str] = None
    category: Optional[str] = None
    fx_rate: Optional[str] = None
    fx_src_ccy: Optional[str] = None
    fx_dst_ccy: Optional[str] = None
    fx_dst_amount: Optional[str] = None
    type: Optional[str] = None


class AccountInfoUSClient:
    def __init__(
        self,
        http: Optional[FinastraHTTP] = None,
        *,
        base_url: Optional[str] = None,
        token_provider: Optional[TokenProvider] = None,
    ) -> None:
        # allow external http (for mocking)
        self._own_http = http is None
        self.http = http or FinastraHTTP(
            base_url=base_url,
            token_provider=token_provider,
            product="account-info-us",
        )

    async def __aenter__(self):
        await self.http.__aenter__()
        return self

    async def __aexit__(self, *exc):
        await self.http.__aexit__(*exc)
        if self._own_http:
            await self.http.aclose()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def list_transactions(
        self,
        account_id: str,
        *,
        from_date: Optional[str] = None,
        to_date: Optional[str] = None,
        limit: int = 100,
    ) -> AsyncIterator[List[Transaction]]:
        """Yield pages of `Transaction` items for the given account.

        Args:
            account_id: External account id.
            from_date: Optional ISO yyyy-mm-dd filter.
            to_date: Optional ISO yyyy-mm-dd filter.
            limit: Page size.
        """

        page = 1
        while True:
            url = f"/corporate/channels/accounts/me/v1/accounts/{account_id}/transactions"
            params = {"page": page, "limit": limit}
            if from_date:
                params["fromBookingDate"] = from_date
            if to_date:
                params["toBookingDate"] = to_date

            resp = await self.http.get(url, params=params)
            data = resp.json()

            items = data.get("items") or []
            tx_page: List[Transaction] = []
            for item in items:
                tx_page.append(
                    Transaction(
                        external_tx_id=item.get("transactionId") or item.get("id"),
                        account_external_id=account_id,
                        raw=item,
                        amount=item.get("transactionAmount"),
                        currency=item.get("currency"),
                        booking_date=item.get("bookingDate"),
                        description=item.get("description"),
                        type=item.get("type"),
                    )
                )

            yield tx_page

            meta = data.get("_meta") or {}
            if page >= int(meta.get("pageCount", 1)):
                break
            page += 1

    async def get_account_details(self, account_id: str) -> Dict:
        """Return raw JSON details for the given account."""
        url = f"/corporate/channels/accounts/me/v1/accounts/{account_id}"
        resp = await self.http.get(url)
        return resp.json()
