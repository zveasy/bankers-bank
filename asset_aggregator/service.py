"""Core async logic for pulling data and publishing snapshots."""
from __future__ import annotations

import asyncio
import json
import os
from datetime import datetime, timezone
from typing import Any, Dict, Optional, Tuple

import httpx
from sqlmodel import Session

from treasury_observability.metrics import (recon_anomalies_total,
                                            snapshot_failure_total,
                                            snapshot_success_total,
                                            treas_ltv_ratio)

from .db import AssetSnapshot, LTVHistory, engine, upsert_assetsnapshot

BALANCES_URL = os.getenv("BALANCES_URL", "http://localhost:9000/balances")
COLLATERAL_URL = os.getenv("COLLATERAL_URL", "http://localhost:9000/collateral")
KAFKA_BOOTSTRAP = os.getenv("KAFKA_BOOTSTRAP", "localhost:9092")
KAFKA_TOPIC = os.getenv("ASSET_TOPIC", "asset_snapshots")


async def balances_puller(bank_id: str) -> Dict[str, Any]:
    """Fetch balances for the given bank id."""
    url = f"{BALANCES_URL}/{bank_id}"
    async with httpx.AsyncClient() as client:
        try:
            resp = await client.get(url, timeout=5)
            resp.raise_for_status()
            return resp.json()
        except Exception:
            return {"totalBalancesUSD": 0.0, "undrawnCreditUSD": 0.0}


async def collateral_puller(bank_id: str) -> Dict[str, Any]:
    """Fetch collateral data for the given bank id."""
    url = f"{COLLATERAL_URL}/{bank_id}"
    async with httpx.AsyncClient() as client:
        try:
            resp = await client.get(url, timeout=5)
            resp.raise_for_status()
            return resp.json()
        except Exception:
            return {"eligibleCollateralUSD": 0.0}


async def publish_snapshot(snapshot: AssetSnapshot) -> None:
    # Allow tests to disable Kafka interaction entirely
    if os.getenv("DISABLE_KAFKA", "0") == "1":
        return
    """Publish snapshot to Kafka if aiokafka is available."""
    try:
        from aiokafka import AIOKafkaProducer
    except Exception:
        return  # silently skip if dependency is unavailable

    producer = AIOKafkaProducer(bootstrap_servers=KAFKA_BOOTSTRAP)
    await producer.start()
    try:
        payload = json.dumps(
            {
                "ts": snapshot.ts.isoformat(),
                "eligibleCollateralUSD": snapshot.eligibleCollateralUSD,
                "totalBalancesUSD": snapshot.totalBalancesUSD,
                "undrawnCreditUSD": snapshot.undrawnCreditUSD,
            }
        ).encode()
        await producer.send_and_wait(
            KAFKA_TOPIC, value=payload, key=snapshot.bank_id.encode()
        )
    finally:
        await producer.stop()


# ------------------ Sprint 6 helpers ------------------


def compute_ltv(
    eligible_collateral_usd: Optional[float], total_balances_usd: Optional[float]
) -> Optional[float]:
    if not eligible_collateral_usd or not total_balances_usd or total_balances_usd <= 0:
        return None
    return float(eligible_collateral_usd) / float(total_balances_usd)


def write_snapshot_idempotent(
    session: Session,
    bank_id: str,
    ts: datetime,
    ec_usd: float,
    tb_usd: float,
    uc_usd: float,
) -> Optional[float]:
    """Upsert AssetSnapshot row and derived LTVHistory."""
    upsert_assetsnapshot(session, bank_id, ts, ec_usd, tb_usd, uc_usd)
    ltv = compute_ltv(ec_usd, tb_usd)
    if ltv is not None:
        session.exec(
            """
            INSERT INTO ltvhistory (bank_id, ts, ltv)
            VALUES (:bank_id, :ts, :ltv)
            ON CONFLICT (bank_id, ts) DO UPDATE SET ltv = EXCLUDED.ltv
            """,
            {"bank_id": bank_id, "ts": ts, "ltv": ltv},
        )
        session.commit()
        treas_ltv_ratio.labels(bank_id=bank_id).set(ltv)
    return ltv


def reconcile_snapshot(
    prev: Dict[str, Any] | None, curr: Dict[str, Any], bank_id: str
) -> None:
    """Simple delta guard emitting recon_anomalies_total."""
    if not prev:
        return
    delta_max_pct = float(os.getenv("RECON_DELTA_MAX_PCT", "0.25"))
    for key in ("eligiblecollateralusd", "totalbalancesusd"):
        pv = prev.get(key)
        cv = curr.get(key)
        if pv is None or cv is None or pv == 0:
            continue
        delta = abs(cv - pv) / abs(pv)
        if delta > delta_max_pct:
            recon_anomalies_total.labels(bank_id=bank_id, type=f"{key}_delta").inc()


# ------------------------------------------------------


async def snapshot_bank_assets(
    bank_id: str, session: Session | None = None
) -> AssetSnapshot:
    """Pull data, persist snapshot, and publish to Kafka."""
    bal_task = balances_puller(bank_id)
    col_task = collateral_puller(bank_id)
    balances, collateral = await asyncio.gather(bal_task, col_task)

    snapshot = AssetSnapshot(
        bank_id=bank_id,
        ts=datetime.now(tz=timezone.utc),
        eligibleCollateralUSD=float(collateral.get("eligibleCollateralUSD", 0.0)),
        totalBalancesUSD=float(balances.get("totalBalancesUSD", 0.0)),
        undrawnCreditUSD=float(balances.get("undrawnCreditUSD", 0.0)),
    )

    with session or Session(engine) as s:
        s.add(snapshot)
        s.commit()
        s.refresh(snapshot)

    if snapshot.eligibleCollateralUSD:
        ratio = snapshot.undrawnCreditUSD / snapshot.eligibleCollateralUSD
        treas_ltv_ratio.labels(bank_id=bank_id).set(ratio)

    await publish_snapshot(snapshot)
    return snapshot


def run_snapshot_once(bank_id: str | None = None) -> Tuple[str, Optional[float]]:
    """Generate mock snapshot, upsert idempotently, return status + derived LTV."""
    bank_id = bank_id or os.getenv("BANK_ID", "demo-bank")
    ts = datetime.now(tz=timezone.utc)
    # mock numbers (replace with real pulls)
    ec_usd, tb_usd, uc_usd = 1_000_000.0, 5_000_000.0, 500_000.0
    try:
        with Session(engine) as s:
            ltv = write_snapshot_idempotent(s, bank_id, ts, ec_usd, tb_usd, uc_usd)
        snapshot_success_total.labels(bank_id=bank_id).inc()
        return ("ok", ltv)
    except Exception:
        snapshot_failure_total.labels(bank_id=bank_id).inc()
        raise
