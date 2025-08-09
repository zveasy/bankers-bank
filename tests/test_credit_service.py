import asyncio
from unittest.mock import AsyncMock

import httpx
from bankersbank.finastra import FinastraAPIClient
from sqlmodel import Session, SQLModel, create_engine, select

from treasury_orchestrator.credit import (CreditFacilityService,
                                          JpmLiquidityClient)
from treasury_orchestrator.credit_db import CreditFacility, CreditTxn


def setup_session() -> Session:
    engine = create_engine("sqlite:///:memory:")
    SQLModel.metadata.create_all(engine)
    return Session(engine)


def test_refresh_capacity(monkeypatch):
    session = setup_session()
    fac = CreditFacility(id="fac1", limit=100000, drawn=0, ltv_limit=0.5)
    session.add(fac)
    session.commit()

    fin = FinastraAPIClient(token="dummy")
    monkeypatch.setattr(
        fin, "collaterals_for_account", lambda _: {"items": [{"valuation": 200000}]}
    )
    jpm = JpmLiquidityClient("http://jpm", "id", "sec", "http://token")

    service = CreditFacilityService(fac, fin, jpm, session)
    asyncio.run(service.refresh_capacity())
    assert service.available == 100000


def test_draw_creates_txn(monkeypatch):
    session = setup_session()
    fac = CreditFacility(id="fac2", limit=50000, drawn=0, ltv_limit=1.0)
    session.add(fac)
    session.commit()

    fin = FinastraAPIClient(token="dummy")
    monkeypatch.setattr(
        fin, "collaterals_for_account", lambda _: {"items": [{"valuation": 50000}]}
    )

    async def fake_post(url, data=None, json=None, headers=None):
        req = httpx.Request("POST", url)
        if "token" in url:
            return httpx.Response(
                status_code=200, json={"access_token": "tok"}, request=req
            )
        return httpx.Response(status_code=201, request=req)

    monkeypatch.setattr(httpx.AsyncClient, "post", AsyncMock(side_effect=fake_post))

    jpm = JpmLiquidityClient("http://jpm", "id", "sec", "http://token")
    service = CreditFacilityService(fac, fin, jpm, session)
    asyncio.run(service.refresh_capacity())
    asyncio.run(service.draw(20000, "USD"))

    assert fac.drawn == 20000
    txns = session.exec(select(CreditTxn)).all()
    assert len(txns) == 1
    assert txns[0].txn_type == "DRAW"
