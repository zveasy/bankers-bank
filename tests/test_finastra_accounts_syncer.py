from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone
from typing import Dict, List

import httpx
import pytest
from sqlmodel import Session, SQLModel, create_engine, select

from asset_aggregator.syncers.finastra_accounts import FinastraAccountsSyncer
from integrations.finastra.accounts_client import AccountsClient
from integrations.finastra.http import FinastraHTTP
from integrations.finastra.auth import TokenProvider
from treasury_domain.account_models import AccountRecord


class _FakeToken(TokenProvider):
    async def token(self) -> str:  # type: ignore[override]
        return "dummy"


# -------------------------------------------------------------------------
# Helpers
# -------------------------------------------------------------------------

def _page(items: List[dict]):
    return {"items": items, "_meta": {"pageCount": 1, "itemCount": len(items)}}


def _account(external_id: str, ctx: str, updated: datetime):
    return {
        "id": external_id,
        "accountContext": ctx,
        "currency": "USD",
        "type": "CURRENT",
        "status": "OPEN",
        "updatedDate": updated.isoformat().replace("+00:00", "Z"),
    }


@pytest.mark.anyio
async def test_accounts_syncer_create_update_skip(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path}/acc.db")
    SQLModel.metadata.create_all(engine)

    t0 = datetime.now(timezone.utc).replace(microsecond=0)
    t1 = t0 + timedelta(hours=1)

    ctx_a = "MT103"
    ctx_b = "INTERNAL-TRANSFER"

    # first run data
    pages: Dict[str, dict] = {
        ctx_a: _page([_account("acc-1", ctx_a, t0)]),
        ctx_b: _page([_account("acc-2", ctx_b, t0)]),
    }

    def handler(request: httpx.Request) -> httpx.Response:  # noqa: D401
        ctx = request.url.params.get("accountContext")
        return httpx.Response(200, json=pages[ctx])

    transport = httpx.MockTransport(handler)
    http = FinastraHTTP(
        base_url="https://api.fusionfabric.cloud",
        token_provider=_FakeToken(),
        transport=transport,
    )
    client = AccountsClient(http=http)

    syncer = FinastraAccountsSyncer(client=client, session_factory=lambda: Session(engine))

    created = await syncer.run_once([ctx_a, ctx_b])
    assert created == 2
    with Session(engine) as s:
        rows = s.exec(select(AccountRecord)).all()
        assert {r.external_id for r in rows} == {"acc-1", "acc-2"}

    # second run: update acc-2 timestamp
    pages[ctx_b] = _page([_account("acc-2", ctx_b, t1)])
    processed = await syncer.run_once([ctx_a, ctx_b])
    assert processed == 2  # processed both rows again
    with Session(engine) as s:
        r1 = s.exec(select(AccountRecord).where(AccountRecord.external_id == "acc-1")).first()
        r2 = s.exec(select(AccountRecord).where(AccountRecord.external_id == "acc-2")).first()
        assert r1.external_updated_ts == t0.replace(tzinfo=None)
        assert r2.external_updated_ts == t1.replace(tzinfo=None)
