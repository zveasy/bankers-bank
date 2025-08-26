from __future__ import annotations

"""Verify audit journal rows are emitted by credit_facility endpoints."""
from datetime import datetime
from typing import Dict

import os
import pytest
from fastapi.testclient import TestClient
from sqlmodel import Session, SQLModel, create_engine, select
from sqlalchemy.pool import StaticPool

# Configure AUDIT_DB_URL BEFORE importing api module
os.environ["AUDIT_DB_URL"] = "sqlite:///:memory:"

from common.audit import AuditJournal, get_engine as _audit_engine  # noqa: E402
from asset_aggregator.db import AssetSnapshot  # noqa: E402
from credit_facility.api import create_app  # noqa: E402
from credit_facility.providers.base import CreditProvider, ProviderResult  # noqa: E402


class StubProvider(CreditProvider):
    async def send_draw(self, bank_id: str, amount: float, currency: str, idem: str) -> ProviderResult:  # type: ignore[override]
        return {"provider_ref": "stub-draw"}

    async def send_repay(self, bank_id: str, amount: float, currency: str, idem: str) -> ProviderResult:  # type: ignore[override]
        return {"provider_ref": "stub-repay"}

    async def get_status(self, bank_id: str) -> Dict:  # type: ignore[override]
        return {"ok": True}


@pytest.fixture()
def app_client():
    engine = create_engine(
        "sqlite:///:memory:",
        echo=False,
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    SQLModel.metadata.create_all(engine)

    def _get_session():
        with Session(engine) as s:
            yield s

    app = create_app()
    import credit_facility.api as api_mod

    app.dependency_overrides[api_mod.get_session] = _get_session  # type: ignore[attr-defined]
    app.dependency_overrides[api_mod.get_provider] = lambda: StubProvider()  # type: ignore[attr-defined]

    return TestClient(app), engine


AUTH = {"Authorization": "Bearer testtoken"}


def _seed(engine):
    with Session(engine) as s:
        s.add(
            AssetSnapshot(
                bank_id="b1",
                ts=datetime.utcnow(),
                eligibleCollateralUSD=1_000_000,
                totalBalancesUSD=1_000_000,
                undrawnCreditUSD=0,
            )
        )
        s.commit()


def test_audit_rows_emitted(app_client):
    client, engine = app_client
    _seed(engine)

    # draw
    client.post(
        "/api/credit/v1/draw",
        headers={"Idempotency-Key": "a1", **AUTH},
        json={"bank_id": "b1", "amount": 100.0},
    )

    # repay
    client.post(
        "/api/credit/v1/repay",
        headers={"Idempotency-Key": "a2", **AUTH},
        json={"bank_id": "b1", "amount": 50.0},
    )

    aud_engine = _audit_engine()
    with Session(aud_engine) as aud_sess:
        rows = aud_sess.exec(select(AuditJournal)).all()  # type: ignore
        actions = [r.action for r in rows]

    assert "CREDIT_DRAW" in actions and "CREDIT_REPAY" in actions
