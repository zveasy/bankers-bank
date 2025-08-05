import os
from datetime import datetime

from sqlmodel import Session, SQLModel, create_engine

from asset_aggregator.db import AssetSnapshot
from credit_facility.models import CreditDraw, CreditRepayment, CreditFacility
from credit_facility.service import CreditFacilityService, _POLICY

# Use in-memory SQLite for fast, isolated tests
engine = create_engine("sqlite:///:memory:", echo=False)
SQLModel.metadata.create_all(engine)


def _seed_snapshot(session: Session, bank_id: str, eligible: float, undrawn: float):
    snap = AssetSnapshot(
        bank_id=bank_id,
        ts=datetime.utcnow(),
        eligibleCollateralUSD=eligible,
        totalBalancesUSD=eligible,  # not relevant here
        undrawnCreditUSD=undrawn,
    )
    session.add(snap)
    session.commit()


def test_capacity_no_outstanding():
    bank = "demo-bank"
    with Session(engine) as s:
        _seed_snapshot(s, bank, eligible=1_000_000, undrawn=0)
        svc = CreditFacilityService(session=s)
        available = svc.capacity(bank)
        cap = _POLICY["banks"][bank]["cap"]
        buffer = _POLICY["banks"][bank]["buffer"]
        assert available == cap - buffer  # undrawn 0 so capacity == default_cap


def test_capacity_with_draws_and_buffer():
    bank = "demo-bank"
    with Session(engine) as s:
        _seed_snapshot(s, bank, eligible=1_000_000, undrawn=0)
        # policy cap 5_000_000, buffer 100_000
        # create one draw 400k and one repayment 50k -> outstanding 350k
        s.add(CreditDraw(idempotency_key="k1", bank_id=bank, amount=400_000, currency="USD"))
        s.add(CreditRepayment(bank_id=bank, amount=50_000, currency="USD"))
        s.commit()
        svc = CreditFacilityService(session=s)
        available = svc.capacity(bank)
        cap = _POLICY["banks"][bank]["cap"]
        buffer = _POLICY["banks"][bank]["buffer"]
        expected = max(cap - 350_000 - buffer, 0)
        assert available == expected
