"""FastAPI endpoints for the Asset Aggregator."""
from __future__ import annotations
import os
from common.logging import configure_logging
configure_logging(os.getenv("LOG_FORMAT", "json"), service_name="asset_aggregator")

import socket
import time
from datetime import datetime, timedelta, timezone
from typing import List
import asyncio

from fastapi import Depends, FastAPI, HTTPException
from common.auth import require_token
from prometheus_client import make_asgi_app
from pydantic import BaseModel
from sqlmodel import Session, select

from treasury_observability.metrics import snapshot_latency_seconds

from .db import AssetSnapshot, engine, init_db
from .service import KAFKA_BOOTSTRAP, reconcile_snapshot, run_snapshot_once
from asset_aggregator.syncers.finastra_collateral import CollateralSyncer
from integrations.finastra.collateral_client import CollateralClient
from asset_aggregator.syncers.finastra_accounts import FinastraAccountsSyncer
from asset_aggregator.syncers.finastra_balances import FinastraBalancesSyncer
from integrations.finastra.accounts_client import AccountsClient
from integrations.finastra.balances_client import BalancesClient

app = FastAPI()
init_db()

app.mount("/metrics", make_asgi_app())


class SnapshotRequest(BaseModel):
    bank_id: str | None = none


@app.get("/healthz", response_model=dict)
async def healthz(_: None = Depends(require_token)):
    # Parse "host:port" from KAFKA_BOOTSTRAP with safe defaults
    host, sep, port = (KAFKA_BOOTSTRAP or "").partition(":")
    host = host or "redpanda"
    port_num = int(port) if port.isdigit() else 9092

    # Try a real metadata probe if kafka-python is present, else TCP fallback
    try:
        try:
            from kafka.admin import KafkaAdminClient  # type: ignore

            client = KafkaAdminClient(
                bootstrap_servers=f"{host}:{port_num}",
                request_timeout_ms=2000,
            )
            client.close()
            return {"ok": True}
        except Exception:
            with socket.create_connection((host, port_num), timeout=2):
                return {"ok": True}
    except Exception as exc:
        raise HTTPException(status_code=503, detail=f"kafka:{exc!s}")


def get_session() -> Session:
    with Session(engine) as session:
        yield session


@app.post("/snapshot")
def create_snapshot(
    payload: SnapshotRequest | None = None,
    bank_id: str | None = None,
    _: None = Depends(require_token),
):
    t0 = time.perf_counter()
    try:
        bank = bank_id or (payload.bank_id if payload else None) or "O&L"
        # fetch previous snapshot for reconciliation
        prev = None
        with Session(engine) as s:
            row = s.exec(
                select(AssetSnapshot)
                .where(AssetSnapshot.bank_id == bank)
                .order_by(AssetSnapshot.ts.desc())
            ).first()
            if row:
                prev = {
                    "eligiblecollateralusd": row.eligibleCollateralUSD,
                    "totalbalancesusd": row.totalBalancesUSD,
                }
        status, ltv = run_snapshot_once(bank)
        # reconcile with mock current values (replace when wiring in real numbers)
        reconcile_snapshot(
            prev,
            {"eligiblecollateralusd": 1_000_000.0, "totalbalancesusd": 5_000_000.0},
            bank,
        )
        # record latency on success
        snapshot_latency_seconds.observe(time.perf_counter() - t0)
        return {"ok": True, "status": status, "ltv": ltv}
    except Exception as e:
        # still record latency on failure
        snapshot_latency_seconds.observe(time.perf_counter() - t0)
        raise HTTPException(status_code=500, detail=f"snapshot_failed: {e}") from e


@app.get("/assets/summary", response_model=AssetSnapshot)
def get_summary(
    bank_id: str,
    session: Session = Depends(get_session),
    _: None = Depends(require_token),
) -> AssetSnapshot:
    row = session.exec(
        select(AssetSnapshot)
        .where(AssetSnapshot.bank_id == bank_id)
        .order_by(AssetSnapshot.ts.desc())
    ).first()
    if not row:
        raise HTTPException(status_code=404, detail="not found")
    return row


@app.get("/assets/history", response_model=List[AssetSnapshot])
def get_history(
    bank_id: str,
    days: int = 1,
    session: Session = Depends(get_session),
    _: None = Depends(require_token),
):
    since = datetime.now(tz=timezone.utc) - timedelta(days=days)
    rows = session.exec(
        select(AssetSnapshot)
        .where(AssetSnapshot.bank_id == bank_id, AssetSnapshot.ts >= since)
        .order_by(AssetSnapshot.ts)
    ).all()
    return rows


# --------------------------------------------------------------------------------------
# Collateral sync trigger (optional operational endpoint)
# --------------------------------------------------------------------------------------


@app.post("/sync/collateral", response_model=dict)
async def run_collateral_sync(_: None = Depends(require_token)):
    """Run Finastra collateral sync once and return #records processed."""
    async def _run() -> int:
        async with CollateralClient() as client:
            syncer = CollateralSyncer(client=client, session_factory=lambda: Session(engine))
            return await syncer.run_once()

    processed = await _run()
    return {"ok": True, "processed": processed}


# --------------------------------------------------------------------------------------
# Accounts and Balances sync triggers
# --------------------------------------------------------------------------------------


class _AccountsPayload(BaseModel):
    contexts: list[str] | None = None


@app.post("/sync/accounts", response_model=dict)
async def run_accounts_sync(payload: _AccountsPayload | None = None, _: None = Depends(require_token)):
    ctxs = payload.contexts if payload else None

    async with AccountsClient() as client:
        syncer = FinastraAccountsSyncer(client=client, session_factory=lambda: Session(engine))
        cnt = await syncer.run_once(ctxs)
    return {"ok": True, "processed": cnt}


class _BalancesPayload(BaseModel):
    accountIds: list[str] | None = None


@app.post("/sync/balances", response_model=dict)
async def run_balances_sync(payload: _BalancesPayload | None = None, _: None = Depends(require_token)):
    ids = payload.accountIds if payload else None
    async with BalancesClient() as client:
        syncer = FinastraBalancesSyncer(client=client, session_factory=lambda: Session(engine))
        cnt = await syncer.run_once(ids)
    return {"ok": True, "processed": cnt}
