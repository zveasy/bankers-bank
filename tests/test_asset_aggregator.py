import asyncio
import json
from datetime import datetime, timezone

import pytest
from sqlmodel import Session, SQLModel, create_engine, select

from asset_aggregator import AssetSnapshot
from asset_aggregator import service as svc


@pytest.fixture
def session(tmp_path):
    engine = create_engine(
        f"sqlite:///{tmp_path}/test.db", connect_args={"check_same_thread": False}
    )
    SQLModel.metadata.create_all(engine)
    with Session(engine) as sess:
        yield sess


@pytest.mark.asyncio
async def test_snapshot_bank_assets(monkeypatch, session):
    async def fake_balances(bank_id: str):
        return {"totalBalancesUSD": 100.0, "undrawnCreditUSD": 50.0}

    async def fake_collateral(bank_id: str):
        return {"eligibleCollateralUSD": 25.0}

    monkeypatch.setattr(svc, "balances_puller", fake_balances)
    monkeypatch.setattr(svc, "collateral_puller", fake_collateral)

    # Mock publish_snapshot to avoid Kafka dependency
    async def fake_publish_snapshot(snapshot):
        return None

    monkeypatch.setattr(svc, "publish_snapshot", fake_publish_snapshot)
    snap = await svc.snapshot_bank_assets("123", session)
    assert isinstance(snap, AssetSnapshot)
    row = session.exec(select(AssetSnapshot)).first()
    assert row.bank_id == "123"
    assert row.totalBalancesUSD == 100.0
    assert row.undrawnCreditUSD == 50.0
    assert row.eligibleCollateralUSD == 25.0


@pytest.fixture(scope="session")
def redpanda_service():
    try:
        from testcontainers.redpanda import RedpandaContainer
    except Exception:
        pytest.skip("Redpanda container not available")
    with RedpandaContainer() as rp:
        yield rp.get_bootstrap_servers()


@pytest.mark.asyncio
async def test_publish_snapshot_kafka(monkeypatch, redpanda_service):
    try:
        from aiokafka import AIOKafkaConsumer
    except Exception:
        pytest.skip("aiokafka not installed")

    snap = AssetSnapshot(
        id=None,
        bank_id="k123",
        ts=datetime.now(tz=timezone.utc),
        eligibleCollateralUSD=1.0,
        totalBalancesUSD=2.0,
        undrawnCreditUSD=3.0,
    )

    monkeypatch.setattr(svc, "KAFKA_BOOTSTRAP", redpanda_service)
    monkeypatch.setattr(svc, "KAFKA_TOPIC", "test_snapshots")

    await svc.publish_snapshot(snap)

    consumer = AIOKafkaConsumer(
        "test_snapshots",
        bootstrap_servers=redpanda_service,
        group_id="t",
        auto_offset_reset="earliest",
    )
    await consumer.start()
    try:
        msg = await consumer.getone()
    finally:
        await consumer.stop()

    assert msg.key == b"k123"
    payload = json.loads(msg.value.decode())
    assert payload["totalBalancesUSD"] == 2.0
