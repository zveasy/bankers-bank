from __future__ import annotations

"""Offline smoke script for Finastra Balances syncer."""

import asyncio
from datetime import datetime, timezone

import httpx
from sqlmodel import SQLModel, create_engine, Session, select

from asset_aggregator.syncers.finastra_balances import FinastraBalancesSyncer
from integrations.finastra.balances_client import BalancesClient
from integrations.finastra.http import FinastraHTTP
from integrations.finastra.auth import TokenProvider
from treasury_domain.account_models import AccountRecord, BalanceRecord


class _FakeToken(TokenProvider):
    async def token(self) -> str:  # type: ignore[override]
        return "dummy"


def _balance(acct_id: str, amt: float):
    now = datetime.now(timezone.utc).replace(microsecond=0)
    return {
        "accountId": acct_id,
        "asOfDate": now.isoformat().replace("+00:00", "Z"),
        "currentAmount": amt,
        "currency": "USD",
    }


async def main():  # noqa: D401
    # mock balances per account
    balances_map = {
        "acc-1": {"items": [_balance("acc-1", 123.45)]},
        "acc-2": {"items": [_balance("acc-2", 678.90)]},
    }

    def handler(request: httpx.Request) -> httpx.Response:  # noqa: D401
        account_id = request.url.path.split("/")[-2]
        return httpx.Response(200, json=balances_map[account_id])

    transport = httpx.MockTransport(handler)
    http = FinastraHTTP(base_url="https://api.mock", token_provider=_FakeToken(), transport=transport)
    client = BalancesClient(http=http)

    engine = create_engine("sqlite:///:memory:")
    SQLModel.metadata.create_all(engine)

    # seed accounts
    with Session(engine) as s:
        s.add(AccountRecord(provider="finastra", external_id="acc-1"))
        s.add(AccountRecord(provider="finastra", external_id="acc-2"))
        s.commit()

    syncer = FinastraBalancesSyncer(client=client, session_factory=lambda: Session(engine))
    processed = await syncer.run_once()
    print(f"Balances processed: {processed}")

    with Session(engine) as s:
        rows = s.exec(select(BalanceRecord)).all()
        print(f"Rows in DB: {len(rows)}")
        for r in rows:
            print(r.account_external_id, r.current_amount, r.as_of_ts)


if __name__ == "__main__":
    asyncio.run(main())
