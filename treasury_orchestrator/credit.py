import asyncio
from typing import Optional

import httpx
try:  # pragma: no cover - optional dependency
    from apscheduler.schedulers.asyncio import AsyncIOScheduler
except Exception:  # pragma: no cover - APScheduler missing
    AsyncIOScheduler = None
from sqlmodel import Session

from bankersbank.finastra import FinastraAPIClient

from .credit_db import CreditFacility, CreditTxn


class JpmLiquidityClient:
    """Minimal JPM liquidity adapter using OAuth2 client credentials."""

    def __init__(self, base_url: str, client_id: str, client_secret: str, token_url: str):
        self.base_url = base_url.rstrip("/")
        self.client_id = client_id
        self.client_secret = client_secret
        self.token_url = token_url
        self._token: Optional[str] = None

    async def token(self) -> str:
        if self._token:
            return self._token
        data = {
            "grant_type": "client_credentials",
            "client_id": self.client_id,
            "client_secret": self.client_secret,
        }
        async with httpx.AsyncClient() as client:
            resp = await client.post(self.token_url, data=data)
            resp.raise_for_status()
            self._token = resp.json()["access_token"]
        return self._token

    async def _headers(self) -> dict:
        return {"Authorization": f"Bearer {await self.token()}"}

    async def post_draw(self, amount: float, currency: str) -> httpx.Response:
        url = f"{self.base_url}/draw"
        async with httpx.AsyncClient() as client:
            resp = await client.post(url, json={"amount": amount, "currency": currency}, headers=await self._headers())
            resp.raise_for_status()
            return resp

    async def post_repay(self, amount: float) -> httpx.Response:
        url = f"{self.base_url}/repay"
        async with httpx.AsyncClient() as client:
            resp = await client.post(url, json={"amount": amount}, headers=await self._headers())
            resp.raise_for_status()
            return resp


class CreditFacilityService:
    """Business logic for managing a credit facility."""

    def __init__(self, facility: CreditFacility, fin_client: FinastraAPIClient, jpm_client: JpmLiquidityClient, session: Session):
        self.facility = facility
        self.fin_client = fin_client
        self.jpm_client = jpm_client
        self.session = session
        self.available: float = 0.0
        self.scheduler: Optional[AsyncIOScheduler] = None

    async def refresh_capacity(self) -> float:
        """Update available capacity based on collateral valuation."""
        data = self.fin_client.collaterals_for_account(self.facility.id)
        total = sum(float(c.get("valuation", 0)) for c in data.get("items", []))
        capacity = min(self.facility.limit, total * self.facility.ltv_limit)
        self.available = max(0.0, capacity - self.facility.drawn)
        return self.available

    async def draw(self, amount: float, currency: str = "USD") -> CreditTxn:
        if amount > self.available:
            raise ValueError("Insufficient capacity")
        await self.jpm_client.post_draw(amount, currency)
        self.facility.drawn += amount
        txn = CreditTxn(facility_id=self.facility.id, amount=amount, txn_type="DRAW")
        self.session.add(self.facility)
        self.session.add(txn)
        self.session.commit()
        await self.refresh_capacity()
        return txn

    async def repay(self, amount: float) -> CreditTxn:
        await self.jpm_client.post_repay(amount)
        self.facility.drawn = max(0.0, self.facility.drawn - amount)
        txn = CreditTxn(facility_id=self.facility.id, amount=amount, txn_type="REPAY")
        self.session.add(self.facility)
        self.session.add(txn)
        self.session.commit()
        await self.refresh_capacity()
        return txn

    def start_scheduler(self) -> None:
        if AsyncIOScheduler is None:
            raise RuntimeError("APScheduler not installed")
        scheduler = AsyncIOScheduler()
        scheduler.add_job(
            lambda: asyncio.create_task(self.refresh_capacity()),
            "interval",
            seconds=900,
        )
        scheduler.start()
        self.scheduler = scheduler


