from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone
from typing import List

import httpx
import pytest
from sqlmodel import SQLModel, create_engine, Session, select

from asset_aggregator.syncers.finastra_collateral import CollateralSyncer
from integrations.finastra.collateral_client import CollateralClient
from integrations.finastra.http import FinastraHTTP
from integrations.finastra.auth import TokenProvider
from treasury_domain.collateral_models import CollateralRecord


class _FakeToken(TokenProvider):
    async def token(self) -> str:  # type: ignore[override]
        return "dummy"


# Helpers -------------------------------------------------

def _page(items: List[dict], next_token: str | None = None):
    return {"items": items, "nextPage": next_token}


def _collateral(i: int, updated: datetime):
    return {
        "collateralId": f"col-{i}",
        "collateralType": "SECURITY",
        "status": "ACTIVE",
        "currency": "USD",
        "nominalAmount": 1000.0,
        "valuationDate": updated.isoformat().replace("+00:00", "Z"),
        "updatedDate": updated.isoformat().replace("+00:00", "Z"),
        "partyId": "BANK1",
    }


@pytest.mark.anyio
async def test_collateral_syncer_create_update_skip(tmp_path):
    # Prepare in-memory DB
    engine = create_engine(f"sqlite:///{tmp_path}/sync.db")
    SQLModel.metadata.create_all(engine)

    t0 = datetime.now(timezone.utc).replace(microsecond=0)
    t1 = t0 + timedelta(hours=1)

    first_page = _page([_collateral(1, t0), _collateral(2, t0)])
    second_page = _page([_collateral(1, t0), _collateral(2, t1)])

    pages = [first_page]

    def handler(request: httpx.Request) -> httpx.Response:  # noqa: D401
        return httpx.Response(200, json=pages[0])

    transport = httpx.MockTransport(handler)
    http = FinastraHTTP(base_url="https://api.fusionfabric.cloud", token_provider=_FakeToken(), transport=transport)
    client = CollateralClient(http=http)

    syncer = CollateralSyncer(client=client, session_factory=lambda: Session(engine))

    # First run: expect 2 created
    created = await syncer.run_once()
    assert created == 2
    with Session(engine) as s:
        rows = s.exec(select(CollateralRecord)).all()
        assert {r.id for r in rows} == {"col-1", "col-2"}
        assert rows[0].external_updated_ts == t0.replace(tzinfo=None)

    # Second run: one updated, one skipped
    pages[0] = second_page
    updated = await syncer.run_once()
    assert updated == 2  # total processed
    with Session(engine) as s:
        r1 = s.get(CollateralRecord, "col-1")
        r2 = s.get(CollateralRecord, "col-2")
        assert r1.external_updated_ts == t0.replace(tzinfo=None)  # unchanged
        assert r2.external_updated_ts == t1.replace(tzinfo=None)  # updated
