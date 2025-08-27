"""Client wrapper for Finastra Collateral APIs (Sprint-11)."""
from __future__ import annotations

from typing import List, Optional, Sequence
from decimal import Decimal

import httpx
from pydantic import BaseModel, Field

from . import PRODUCT_COLLATERAL, TENANT
from .http import FinastraHTTP
from treasury_domain.collateral_models import FinastraCollateral


class _Page(BaseModel):
    items: Sequence[dict] = Field(default_factory=list)
    nextPage: Optional[str] = None  # Finastra convention


class CollateralClient:
    """Typed async client for collateral endpoints."""

    def __init__(self, http: Optional[FinastraHTTP] = None):
        self._http = http or FinastraHTTP()

    async def list_collaterals(
        self, *, page_token: str | None = None, page_size: int = 100
    ) -> tuple[List[FinastraCollateral], Optional[str]]:
        path = f"/collateral/v2/{TENANT}/collaterals"  # from Postman but paramisable
        params = {"pageSize": page_size}
        if page_token:
            params["pageToken"] = page_token
        resp: httpx.Response = await self._http.get(path, params=params)
        page = _Page.parse_obj(resp.json())
        collaterals = [FinastraCollateral(raw=obj, **self._map_fields(obj)) for obj in page.items]
        return collaterals, page.nextPage

    @staticmethod
    def _parse_ts(val):
        from datetime import datetime, timezone
        if not val:
            return None
        if isinstance(val, datetime):
            return val
        try:
            dt = datetime.fromisoformat(val.replace("Z", "+00:00"))
            return dt.astimezone(timezone.utc).replace(tzinfo=None)
        except ValueError:
            return None

    @staticmethod
    def _map_fields(data: dict) -> dict:
        return {
            "id": data.get("collateralId") or data.get("id"),
            "kind": data.get("collateralType"),
            "status": data.get("status"),
            "currency": data.get("currency"),
                        "amount": Decimal(str(data.get("nominalAmount"))) if data.get("nominalAmount") is not None else None,
            "valuation_ts": CollateralClient._parse_ts(data.get("valuationDate")),
            "external_updated_ts": CollateralClient._parse_ts(data.get("updatedDate")),
            "bank_id": data.get("partyId"),
        }

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        await self._http.aclose()
