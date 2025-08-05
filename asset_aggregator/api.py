"""FastAPI endpoints for the Asset Aggregator."""
from __future__ import annotations

import socket
import time
from datetime import datetime, timedelta, timezone
from typing import List, Optional

from fastapi import FastAPI, Depends, HTTPException, Query
from sqlmodel import Session, select

from .db import engine, AssetSnapshot, init_db
from .service import run_snapshot_once, KAFKA_BOOTSTRAP
from treasury_observability.metrics import snapshot_latency_seconds
from prometheus_client import make_asgi_app

app = FastAPI()
init_db()

app.mount("/metrics", make_asgi_app())


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
def create_snapshot(bank_id: str | None = None):
    try:
        res = run_snapshot_once(bank_id)
        return {"ok": True, "result": res}
    except Exception as e:
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
