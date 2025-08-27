from __future__ import annotations

import json

import httpx
import pytest
from integrations.finastra.collateral_client import CollateralClient


@pytest.mark.asyncio
async def test_list_collaterals_parses_page(monkeypatch):
    sample = {
        "items": [
            {
                "collateralId": "C1",
                "collateralType": "CASH",
                "status": "ACTIVE",
                "currency": "USD",
                "nominalAmount": 1000.0,
                "valuationDate": "2025-08-20T00:00:00Z",
                "updatedDate": "2025-08-21T00:00:00Z",
                "partyId": "BANK123",
            }
        ],
        "nextPage": None,
    }

    async def handler(request):  # noqa: D401
        return httpx.Response(200, json=sample)

    transport = httpx.MockTransport(handler)
    async with CollateralClient() as client:
        client._http._client._transport = transport  # type: ignore
        rows, next_token = await client.list_collaterals()

    assert next_token is None
    assert len(rows) == 1
    assert rows[0].id == "C1"
    assert rows[0].amount == 1000.0
