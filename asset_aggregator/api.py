"""FastAPI endpoints for the Asset Aggregator."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from fastapi import FastAPI, Depends, HTTPException
from sqlmodel import Session, select

from .db import engine, AssetSnapshot, init_db
from .service import run_snapshot_once, KAFKA_BOOTSTRAP

app = FastAPI()
init_db()


@app.get("/healthz")
async def healthz():
    try:
        from kafka.admin import KafkaAdminClient

        client = KafkaAdminClient(bootstrap_servers=KAFKA_BOOTSTRAP)
        client.close()
        return {"ok": True}
    except Exception as exc:
        raise HTTPException(status_code=503, detail=f"kafka:{exc}")


def get_session() -> Session:
    with Session(engine) as session:
        yield session


@app.post("/snapshot")
def create_snapshot(bank_id: str | None = None):
    return run_snapshot_once(bank_id)


@app.get("/assets/summary")
def get_summary(bank_id: str, session: Session = Depends(get_session)) -> AssetSnapshot:
    row = session.exec(
        select(AssetSnapshot)
        .where(AssetSnapshot.bank_id == bank_id)
        .order_by(AssetSnapshot.ts.desc())
    ).first()
    if not row:
        raise HTTPException(status_code=404, detail="not found")
    return row


@app.get("/assets/history")
def get_history(bank_id: str, days: int = 1, session: Session = Depends(get_session)):
    since = datetime.now(tz=timezone.utc) - timedelta(days=days)
    rows = session.exec(
        select(AssetSnapshot)
        .where(AssetSnapshot.bank_id == bank_id, AssetSnapshot.ts >= since)
        .order_by(AssetSnapshot.ts)
    ).all()
    return rows
