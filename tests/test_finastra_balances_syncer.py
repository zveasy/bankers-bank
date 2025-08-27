from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone
from typing import Dict, List

import httpx
import pytest
from sqlmodel import Session, SQLModel, create_engine, select

from asset_aggregator.syncers.finastra_balances import FinastraBalancesSyncer
from integrations.finastra.balances_client import BalancesClient
from integrations.finastra.http import FinastraHTTP
from integrations.finastra.auth import TokenProvider
from treasury_domain.account_models import BalanceRecord, AccountRecord


class _FakeToken(TokenProvider):
    async def token(self) -> str:  # type: ignore[override]
        return "dummy"


# -------------------------------------------------------------------------
# Helpers
# -------------------------------------------------------------------------

def _balance(acct_id: str, as_of: datetime, cur_amt: float):
    return {
        "accountId": acct_id,
        "asOfDate": as_of.isoformat().replace("+00:00", "Z"),
        "currentAmount": cur_amt,
        "currency": "USD",
    }


@pytest.mark.anyio
async def test_balances_syncer_create_update_skip(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path}/bal.db")
    SQLModel.metadata.create_all(engine)

    # seed one account row so balance syncer fetches account ids
    with Session(engine) as s:
        s.add(AccountRecord(provider="finastra", external_id="acc-1"))
        s.commit()

    t0 = datetime.now(timezone.utc).replace(microsecond=0)
    t1 = t0 + timedelta(hours=2)

    # transport handler mapping accountId -> json response
    balances_payloads: Dict[str, dict] = {
        "acc-1": {"items": [_balance("acc-1", t0, 100.0)]}
    }

    def handler(request: httpx.Request) -> httpx.Response:  # noqa: D401
        account_id = request.url.path.split("/")[-2]
        return httpx.Response(200, json=balances_payloads[account_id])

    transport = httpx.MockTransport(handler)
    http = FinastraHTTP(base_url="https://api.fusionfabric.cloud", token_provider=_FakeToken(), transport=transport)
    client = BalancesClient(http=http)

    syncer = FinastraBalancesSyncer(client=client, session_factory=lambda: Session(engine))

    created = await syncer.run_once()
    assert created == 1
    with Session(engine) as s:
        row = s.exec(select(BalanceRecord)).first()
        assert row.current_amount == 100.0

    # update currentAmount value in second run
    balances_payloads["acc-1"] = {"items": [_balance("acc-1", t0, 150.0)]}
    processed = await syncer.run_once()
    assert processed == 1
    with Session(engine) as s:
        row = s.exec(select(BalanceRecord)).first()
        assert row.current_amount == 150.0
        # add new timestamp balance
    balances_payloads["acc-1"] = {"items": [_balance("acc-1", t1, 200.0)]}
    processed2 = await syncer.run_once()
    assert processed2 == 1  # one new row created
    with Session(engine) as s:
        rows = s.exec(select(BalanceRecord)).all()
        assert len(rows) == 2
