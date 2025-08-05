"""FastAPI endpoints for the Asset Aggregator."""
from __future__ import annotations

import socket
import time
from datetime import datetime, timedelta, timezone
from typing import List

from fastapi import FastAPI, Depends, HTTPException
from pydantic import BaseModel
from sqlmodel import Session, select

from .db import engine, AssetSnapshot, init_db
from .service import run_snapshot_once, KAFKA_BOOTSTRAP, reconcile_snapshot
from treasury_observability.metrics import snapshot_latency_seconds
from prometheus_client import make_asgi_app

app = FastAPI()
init_db()

app.mount("/metrics", make_asgi_app())

class SnapshotRequest(BaseModel):
    bank_id: str | None = none


@app.get("/healthz", response_model=dict)
async def healthz():
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
def create_snapshot(payload: SnapshotRequest | None = None, bank_id: str | None = None):
    t0 = time.perf_counter()
    try:
        bank = (bank_id or (payload.bank_id if payload else None) or "O&L")
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
        reconcile_snapshot(prev, {"eligiblecollateralusd": 1_000_000.0, "totalbalancesusd": 5_000_000.0}, bank)
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
):
    since = datetime.now(tz=timezone.utc) - timedelta(days=days)
    rows = session.exec(
        select(AssetSnapshot)
        .where(AssetSnapshot.bank_id == bank_id, AssetSnapshot.ts >= since)
        .order_by(AssetSnapshot.ts)
    ).all()
    return rows
