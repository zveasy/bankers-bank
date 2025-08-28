from __future__ import annotations
"""Offline smoke script for Finastra Transactions syncer.
Validates end-to-end ingestion into SQLite using mock transport.
"""

import asyncio
from datetime import datetime, timezone

import httpx
from sqlmodel import SQLModel, create_engine, Session, select

from asset_aggregator.syncers.finastra_transactions import FinastraTransactionsSyncer
from integrations.finastra.account_info_us_client import AccountInfoUSClient
from integrations.finastra.http import FinastraHTTP
from integrations.finastra.auth import TokenProvider
from treasury_domain.transaction_models import AccountTransactionRecord


class _FakeToken(TokenProvider):
    async def token(self) -> str:  # type: ignore[override]
        return "dummy"


def _sample_page(acct_id: str):
    now = datetime.now(timezone.utc).replace(microsecond=0)
    return {
        "items": [
            {
                "transactionId": "tx-1",
                "bookingDate": now.isoformat().replace("+00:00", "Z"),
                "transactionAmount": 42.0,
                "currency": "USD",
            }
        ],
        "_meta": {"pageCount": 1, "itemCount": 1},
    }


async def main():  # noqa: D401
    acct_id = "acc-1"

    # transport handler
    def handler(request: httpx.Request) -> httpx.Response:  # noqa: D401
        return httpx.Response(200, json=_sample_page(acct_id))

    transport = httpx.MockTransport(handler)
    http = FinastraHTTP(base_url="https://api.mock", token_provider=_FakeToken(), transport=transport)
    client = AccountInfoUSClient(http=http)

    engine = create_engine("sqlite:///:memory:")
    SQLModel.metadata.create_all(engine)

    syncer = FinastraTransactionsSyncer(client=client, session_factory=lambda: Session(engine))
    processed = await syncer.run_once([acct_id])
    print(f"Transactions processed: {processed}")

    with Session(engine) as s:
        rows = s.exec(select(AccountTransactionRecord)).all()
        print(f"Rows in DB: {len(rows)}")
        for r in rows:
            print(r.external_tx_id, r.amount, r.booking_date)


if __name__ == "__main__":
    asyncio.run(main())
