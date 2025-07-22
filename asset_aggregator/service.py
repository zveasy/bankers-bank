"""Core async logic for pulling data and publishing snapshots."""
from __future__ import annotations

import asyncio
import json
import os
from datetime import datetime, timezone
from typing import Any, Dict

import httpx
from sqlmodel import Session

from .db import AssetSnapshot, engine

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
        await producer.send_and_wait(KAFKA_TOPIC, value=payload, key=snapshot.bank_id.encode())
    finally:
        await producer.stop()


async def snapshot_bank_assets(bank_id: str, session: Session | None = None) -> AssetSnapshot:
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

    with (session or Session(engine)) as s:
        s.add(snapshot)
        s.commit()
        s.refresh(snapshot)

    await publish_snapshot(snapshot)
    return snapshot
