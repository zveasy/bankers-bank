from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone
from typing import Dict, List

import httpx
import pytest
from sqlmodel import Session, SQLModel, create_engine, select

from asset_aggregator.syncers.finastra_transactions import FinastraTransactionsSyncer
from integrations.finastra.account_info_us_client import AccountInfoUSClient, Transaction
from integrations.finastra.http import FinastraHTTP
from integrations.finastra.auth import TokenProvider
from treasury_domain.transaction_models import AccountTransactionRecord


class _FakeToken(TokenProvider):
    async def token(self) -> str:  # type: ignore[override]
        return "dummy"


# -------------------------------------------------------------------------
# Helpers
# -------------------------------------------------------------------------

def _tx(tx_id: str, acct_id: str, booking: datetime, amount: float):
    return {
        "transactionId": tx_id,
        "bookingDate": booking.isoformat().replace("+00:00", "Z"),
        "transactionAmount": amount,
        "currency": "USD",
    }


def _page(items: List[dict]):
    return {"items": items, "_meta": {"pageCount": 1, "itemCount": len(items)}}


@pytest.mark.anyio
async def test_transactions_syncer_create_update_skip(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path}/tx.db")

    acct_id = "acc-1"
    t0 = datetime.now(timezone.utc).replace(microsecond=0)
    t1 = t0 + timedelta(days=1)

    pages: Dict[str, dict] = {
        acct_id: _page([_tx("tx-1", acct_id, t0, 50.0)])
    }

    def handler(request: httpx.Request) -> httpx.Response:  # noqa: D401
        account_id = request.url.path.split("/")[-2]
        return httpx.Response(200, json=pages[account_id])

    transport = httpx.MockTransport(handler)
    http = FinastraHTTP(base_url="https://api.mock", token_provider=_FakeToken(), transport=transport)
    client = AccountInfoUSClient(http=http)

    # ensure tables exist after models imported
    SQLModel.metadata.create_all(engine)

    syncer = FinastraTransactionsSyncer(client=client, session_factory=lambda: Session(engine))

    created = await syncer.run_once([acct_id])
    assert created == 1
    with Session(engine) as s:
        rows = s.exec(select(AccountTransactionRecord)).all()
        assert len(rows) == 1
        assert rows[0].amount == 50.0

    # update amount value (source hash changes) on second run
    pages[acct_id] = _page([_tx("tx-1", acct_id, t0, 75.0)])
    processed = await syncer.run_once([acct_id])
    assert processed == 1
    with Session(engine) as s:
        row = s.exec(select(AccountTransactionRecord)).first()
        assert row.amount == 75.0

    # new booking date creates new row
    pages[acct_id] = _page([_tx("tx-2", acct_id, t1, 25.0)])
    processed2 = await syncer.run_once([acct_id])
    assert processed2 == 1
    with Session(engine) as s:
        rows = s.exec(select(AccountTransactionRecord)).all()
        assert len(rows) == 2
