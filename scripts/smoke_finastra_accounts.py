from __future__ import annotations

"""Offline smoke script for Finastra Accounts syncer.
Runs against mock transport and in-memory SQLite to validate the pipeline end-to-end.
"""

import asyncio
from datetime import datetime, timezone

import httpx
from sqlmodel import SQLModel, create_engine, Session, select

from asset_aggregator.syncers.finastra_accounts import FinastraAccountsSyncer
from integrations.finastra.accounts_client import AccountsClient
from integrations.finastra.http import FinastraHTTP
from integrations.finastra.auth import TokenProvider
from treasury_domain.account_models import AccountRecord


class _FakeToken(TokenProvider):
    async def token(self) -> str:  # type: ignore[override]
        return "dummy"


def _sample_page(ctx: str):
    now = datetime.now(timezone.utc).replace(microsecond=0)
    return {
        "items": [
            {
                "id": f"acc-{ctx}-1",
                "accountContext": ctx,
                "currency": "USD",
                "type": "CURRENT",
                "status": "OPEN",
                "updatedDate": now.isoformat().replace("+00:00", "Z"),
            }
        ],
        "_meta": {"pageCount": 1, "itemCount": 1},
    }


async def main():  # noqa: D401
    # mock transport handler
    ctx_pages = {"MT103": _sample_page("MT103"), "INTERNAL-TRANSFER": _sample_page("INTERNAL-TRANSFER")}

    def handler(request: httpx.Request) -> httpx.Response:  # noqa: D401
        ctx = request.url.params.get("accountContext")
        return httpx.Response(200, json=ctx_pages[ctx])

    transport = httpx.MockTransport(handler)
    http = FinastraHTTP(base_url="https://api.mock", token_provider=_FakeToken(), transport=transport)
    client = AccountsClient(http=http)

    engine = create_engine("sqlite:///:memory:")
    SQLModel.metadata.create_all(engine)

    syncer = FinastraAccountsSyncer(client=client, session_factory=lambda: Session(engine))
    processed = await syncer.run_once(["MT103", "INTERNAL-TRANSFER"])
    print(f"Accounts processed: {processed}")

    with Session(engine) as s:
        rows = s.exec(select(AccountRecord)).all()
        print(f"Rows in DB: {len(rows)}")
        for r in rows:
            print(r.external_id, r.context, r.currency)


if __name__ == "__main__":
    asyncio.run(main())
