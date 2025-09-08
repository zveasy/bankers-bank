from __future__ import annotations

"""Integration tests for credit action API (Sprint 7 / PR-2)."""
from datetime import datetime
from typing import Dict

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine

from asset_aggregator.db import AssetSnapshot
from credit_facility.api import create_app
from credit_facility.providers.base import CreditProvider, ProviderResult

# ---------------------------------------------------------------------------
# Stub provider with deterministic refs
# ---------------------------------------------------------------------------


class StubProvider(CreditProvider):
    async def send_draw(self, bank_id: str, amount: float, currency: str, idem: str) -> ProviderResult:  # type: ignore[override]
        return {"provider_ref": f"stub-draw-{idem}"}

    async def send_repay(self, bank_id: str, amount: float, currency: str, idem: str) -> ProviderResult:  # type: ignore[override]
        return {"provider_ref": f"stub-repay-{idem}"}

    async def get_status(self, bank_id: str) -> Dict:  # type: ignore[override]
        return {"ok": True}


@pytest.fixture()
def app_client():
    """FastAPI test client with isolated in-memory DB and stub provider."""
    engine = create_engine(
        "sqlite:///:memory:",
        echo=False,
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    SQLModel.metadata.create_all(engine)

    # override get_session and get_provider
    def _get_session():
        with Session(engine) as session:
            yield session

    app = create_app()
    import credit_facility.api as api_module

    app.dependency_overrides[api_module.get_session] = _get_session  # type: ignore[attr-defined]
    app.dependency_overrides[api_module.get_provider] = lambda: StubProvider()  # type: ignore[attr-defined]

    # ensure all models tables exist after all imports
    SQLModel.metadata.create_all(engine)
    return TestClient(app), engine


AUTH = {"Authorization": "Bearer testtoken"}


def _seed_snapshot(session: Session, bank_id: str = "b1") -> None:
    snap = AssetSnapshot(
        bank_id=bank_id,
        ts=datetime.utcnow(),
        eligibleCollateralUSD=1_000_000.0,
        totalBalancesUSD=1_000_000.0,
        undrawnCreditUSD=0.0,
    )
    session.add(snap)
    session.commit()


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


def test_draw_happy_path(app_client):
    client, engine = app_client
    with Session(engine) as s:
        _seed_snapshot(s)
    resp = client.post(
        "/api/credit/v1/draw",
        headers={"Idempotency-Key": "idx1", **AUTH},
        json={"bank_id": "b1", "amount": 1000.0},
    )
    assert resp.status_code == 201, resp.text
    data = resp.json()
    assert data["status"] == "POSTED"
    assert data["outstanding"] >= 1000.0


def test_draw_idempotent(app_client):
    client, engine = app_client
    with Session(engine) as s:
        _seed_snapshot(s)
    payload = {"bank_id": "b1", "amount": 500.0}
    h = {"Idempotency-Key": "idem-1"}
    first = client.post("/api/credit/v1/draw", headers={**h, **AUTH}, json=payload)
    second = client.post("/api/credit/v1/draw", headers={**h, **AUTH}, json=payload)
    assert first.status_code == 201 and second.status_code == 201
    assert first.json()["provider_ref"] == second.json()["provider_ref"]


def test_repay_happy_path(app_client):
    client, engine = app_client
    with Session(engine) as s:
        _seed_snapshot(s)
    client.post(
        "/api/credit/v1/draw",
        headers={"Idempotency-Key": "d2", **AUTH},
        json={"bank_id": "b1", "amount": 200.0},
    )
    resp = client.post(
        "/api/credit/v1/repay",
        headers={"Idempotency-Key": "r1", **AUTH},
        json={"bank_id": "b1", "amount": 100.0},
    )
    assert resp.status_code == 201
    assert resp.json()["status"] == "POSTED"


def test_status_endpoint(app_client):
    client, engine = app_client
    with Session(engine) as s:
        _seed_snapshot(s)
    client.post(
        "/api/credit/v1/draw",
        headers={"Idempotency-Key": "s1", **AUTH},
        json={"bank_id": "b1", "amount": 110.0},
    )
    client.post(
        "/api/credit/v1/repay",
        headers={"Idempotency-Key": "s2", **AUTH},
        json={"bank_id": "b1", "amount": 10.0},
    )
    r = client.get("/api/credit/v1/b1/status", headers=AUTH)
    assert r.status_code == 200
    body = r.json()
    assert body["bank_id"] == "b1"
    assert len(body["last_actions"]) > 0


def test_credit_draw_unauthorized(app_client):
    client, engine = app_client
    with Session(engine) as s:
        _seed_snapshot(s)
    resp = client.post(
        "/api/credit/v1/draw",
        headers={"Idempotency-Key": "z1"},
        json={"bank_id": "b1", "amount": 100.0},
    )
    assert resp.status_code == 401
