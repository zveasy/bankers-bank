from __future__ import annotations

"""Offline smoke test for Finastra Collateral integration.

Usage (offline default):
    poetry run python scripts/smoke_finastra_collateral.py --offline

When --offline is given, the script patches the HTTP transport with a stubbed
`httpx.MockTransport` serving a static fixture so it can run without network.
The script writes to an in-memory SQLite DB and prints the number of records
created/updated along with a simple summary.
"""

import argparse
import asyncio
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import List

import httpx
from sqlmodel import SQLModel, Session, create_engine, select

from asset_aggregator.syncers.finastra_collateral import CollateralSyncer
from integrations.finastra.collateral_client import CollateralClient
from integrations.finastra.http import FinastraHTTP
from integrations.finastra.auth import TokenProvider
from treasury_domain.collateral_models import CollateralRecord

_FIXTURE = {
    "items": [
        {
            "collateralId": "col-1",
            "collateralType": "SECURITY",
            "status": "ACTIVE",
            "currency": "USD",
            "nominalAmount": 1000.0,
            "valuationDate": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
            "updatedDate": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
            "partyId": "BANK1",
        }
    ],
    "nextPage": None,
}


class _StaticToken(TokenProvider):
    async def token(self) -> str:  # type: ignore[override]
        return "dummy"


def _offline_http() -> FinastraHTTP:
    def handler(request: httpx.Request) -> httpx.Response:  # noqa: D401
        return httpx.Response(200, json=_FIXTURE)

    transport = httpx.MockTransport(handler)
    return FinastraHTTP(token_provider=_StaticToken(), transport=transport)


def run_smoke(offline: bool = True) -> None:
    # Create isolated sqlite DB under tmp
    engine = create_engine("sqlite:///:memory:")
    SQLModel.metadata.create_all(engine)

    http_client = _offline_http() if offline else FinastraHTTP()
    collateral_client = CollateralClient(http=http_client)
    syncer = CollateralSyncer(client=collateral_client, session_factory=lambda: Session(engine))

    created = asyncio.run(syncer.run_once())
    with Session(engine) as s:
        rows: List[CollateralRecord] = s.exec(select(CollateralRecord)).all()

    print("Smoke result -> created", created, "rows", len(rows))
    for r in rows:
        print(json.dumps(r.raw, indent=2))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Offline smoke test for Finastra Collateral sync")
    parser.add_argument("--offline", action="store_true", default=False, help="Run with mock transport (default)")
    args = parser.parse_args()
    run_smoke(offline=args.offline or True)
