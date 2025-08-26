from __future__ import annotations

"""Async client for Finastra Accounts product.

Only the subset needed for batch sync is implemented. Pagination follows the
`_meta.pageCount` pattern of Finastra APIs. Designed for easy mocking via
`httpx.MockTransport`.
"""

import asyncio
from dataclasses import dataclass
from typing import AsyncIterator, Dict, List, Optional

import httpx

from .auth import TokenProvider
from .http import FinastraHTTP

__all__ = ["Account", "AccountsClient"]


@dataclass(slots=True)
class Account:
    """DTO representing a single Finastra account item."""

    external_id: str
    raw: Dict

    # parsed convenience fields (optional)
    currency: Optional[str] = None
    context: Optional[str] = None
    type: Optional[str] = None
    status: Optional[str] = None
    updated: Optional[str] = None  # ISO string


class AccountsClient:
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
            product="accounts",
        )

    async def __aenter__(self):
        await self.http.__aenter__()
        return self

    async def __aexit__(self, *exc):
        await self.http.__aexit__(*exc)
        if self._own_http:
            await self.http.aclose()

    # ---------------------------------------------------------------------
    # Public API
    # ---------------------------------------------------------------------

    async def list_accounts(
        self,
        account_context: str,
        *,
        limit: int = 50,
    ) -> AsyncIterator[List[Account]]:
        """Yield pages of `Account` items for the given context."""

        page = 1
        while True:
            url = f"/corporate/channels/accounts/me/v1/accounts"
            params = {
                "accountContext": account_context,
                "page": page,
                "limit": limit,
            }
            resp = await self.http.get(url, params=params)
            data = resp.json()

            items = data.get("items") or []
            accounts_page: List[Account] = []
            for item in items:
                accounts_page.append(
                    Account(
                        external_id=item.get("id") or item.get("accountId"),
                        raw=item,
                        currency=item.get("currency"),
                        context=item.get("accountContext"),
                        type=item.get("type"),
                        status=item.get("status"),
                        updated=item.get("updatedDate"),
                    )
                )

            yield accounts_page

            meta = data.get("_meta") or {}
            if page >= int(meta.get("pageCount", 1)):
                break
            page += 1

    # convenience helper for simple cases
    async def iter_all_accounts(
        self, contexts: List[str], *, limit: int = 50
    ) -> AsyncIterator[Account]:
        for ctx in contexts:
            async for page in self.list_accounts(ctx, limit=limit):
                for acc in page:
                    yield acc
