"""FastAPI endpoints for the Asset Aggregator."""
from __future__ import annotations
import os
from common.logging import configure_logging
configure_logging(os.getenv("LOG_FORMAT", "json"), service_name="asset_aggregator")

import socket
import time
import logging
from datetime import datetime, timedelta, timezone
from typing import List, Optional
import asyncio

from fastapi import Depends, FastAPI, HTTPException, Query, Path
from common.auth import require_token
from prometheus_client import make_asgi_app
from pydantic import BaseModel
from sqlmodel import Session, select

from treasury_observability.metrics import snapshot_latency_seconds

from .db import AssetSnapshot, engine, init_db
from .service import KAFKA_BOOTSTRAP, reconcile_snapshot, run_snapshot_once
from asset_aggregator.syncers.finastra_collateral import CollateralSyncer
from integrations.finastra.collateral_client import CollateralClient
from asset_aggregator.syncers.finastra_accounts import FinastraAccountsSyncer
from asset_aggregator.syncers.finastra_balances import FinastraBalancesSyncer
from integrations.finastra.accounts_client import AccountsClient
from integrations.finastra.balances_client import BalancesClient
from asset_aggregator.syncers.finastra_transactions import FinastraTransactionsSyncer
from integrations.finastra.account_info_us_client import AccountInfoUSClient
from bankersbank.finastra import (
    ClientCredentialsTokenProvider,
    FinastraAPIClient,
    FINASTRA_BASE_URL,
    FINASTRA_TENANT,
)

app = FastAPI()
init_db()

app.mount("/metrics", make_asgi_app())

#
# Read model to avoid FastAPI/Pydantic recursion with table=True models
# Fields mirror your AssetSnapshot attributes (camelCase names included).
#
from sqlmodel import SQLModel

class AssetSnapshotRead(SQLModel):
    bank_id: str
    ts: datetime
    eligibleCollateralUSD: Optional[float] = None
    totalBalancesUSD: Optional[float] = None
    undrawnCreditUSD: Optional[float] = None

class SnapshotRequest(BaseModel):
    bank_id: str | None = None


@app.get("/healthz", response_model=dict)
async def healthz(_: None = Depends(require_token)):
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
def create_snapshot(
    payload: SnapshotRequest | None = None,
    bank_id: str | None = None,
    _: None = Depends(require_token),
):
    t0 = time.perf_counter()
    try:
        bank = bank_id or (payload.bank_id if payload else None) or "O&L"
        # fetch previous snapshot for reconciliation
        prev = None
        with Session(engine) as s:
            row = s.exec(
                select(AssetSnapshot)
                .where(AssetSnapshot.bank_id == bank)
                .order_by(AssetSnapshot.ts.desc())
            ).first()
            if row:
                prev = {
                    "eligiblecollateralusd": row.eligibleCollateralUSD,
                    "totalbalancesusd": row.totalBalancesUSD,
                }
        status, ltv = run_snapshot_once(bank)
        # reconcile with mock current values (replace when wiring in real numbers)
        reconcile_snapshot(
            prev,
            {"eligiblecollateralusd": 1_000_000.0, "totalbalancesusd": 5_000_000.0},
            bank,
        )
        # record latency on success
        snapshot_latency_seconds.observe(time.perf_counter() - t0)
        return {"ok": True, "status": status, "ltv": ltv}
    except Exception as e:
        # still record latency on failure
        snapshot_latency_seconds.observe(time.perf_counter() - t0)
        raise HTTPException(status_code=500, detail=f"snapshot_failed: {e}") from e


@app.get("/assets/summary", response_model=AssetSnapshotRead)
def get_summary(
    bank_id: str,
    session: Session = Depends(get_session),
    _: None = Depends(require_token),
) -> AssetSnapshotRead:
    row = session.exec(
        select(AssetSnapshot)
        .where(AssetSnapshot.bank_id == bank_id)
        .order_by(AssetSnapshot.ts.desc())
    ).first()
    if not row:
        raise HTTPException(status_code=404, detail="not found")
    return row


@app.get("/assets/history", response_model=List[AssetSnapshotRead])
def get_history(
    bank_id: str,
    days: int = 1,
    session: Session = Depends(get_session),
    _: None = Depends(require_token),
):
    since = datetime.now(tz=timezone.utc) - timedelta(days=days)
    rows = session.exec(
        select(AssetSnapshot)
        .where(AssetSnapshot.bank_id == bank_id, AssetSnapshot.ts >= since)
        .order_by(AssetSnapshot.ts)
    ).all()
    return rows


# --------------------------------------------------------------------------------------
# Collateral sync trigger (optional operational endpoint)
# --------------------------------------------------------------------------------------


@app.post("/sync/collateral", response_model=dict)
async def run_collateral_sync(_: None = Depends(require_token)):
    """Run Finastra collateral sync once and return #records processed."""
    async def _run() -> int:
        async with CollateralClient() as client:
            syncer = CollateralSyncer(client=client, session_factory=lambda: Session(engine))
            return await syncer.run_once()

    processed = await _run()
    return {"ok": True, "processed": processed}


# --------------------------------------------------------------------------------------
# Finastra B2B – Collaterals (list/get)
# --------------------------------------------------------------------------------------


def _fin_client() -> FinastraAPIClient:
    """Builds a FinastraAPIClient using env configuration.

    Expects FINASTRA_CLIENT_ID/FINASTRA_CLIENT_SECRET to be present in env
    (see docs/runbooks/finastra.md). Uses default scope "accounts".
    """
    strategy = os.getenv("FINASTRA_TOKEN_STRATEGY", "client_credentials").lower()
    static_bearer = os.getenv("FINASTRA_STATIC_BEARER")

    # Prefer static bearer when explicitly configured
    if strategy == "static" and static_bearer and static_bearer != "disabled":
        return FinastraAPIClient(
            base_url=FINASTRA_BASE_URL,
            tenant=FINASTRA_TENANT,
            token=static_bearer,
        )

    # Fall back to client-credentials
    provider = ClientCredentialsTokenProvider(
        base_url=FINASTRA_BASE_URL,
        tenant=FINASTRA_TENANT,
        client_id=os.environ.get("FINASTRA_CLIENT_ID"),
        client_secret=os.environ.get("FINASTRA_CLIENT_SECRET"),
        scope=os.getenv("FINASTRA_SCOPE", "accounts"),
        verify=os.getenv("CA_CERT", True),
    )
    return FinastraAPIClient(token_provider=provider)


def _feature_enabled() -> bool:
    return os.getenv("FEATURE_FINASTRA_COLLATERALS", "1").lower() in ("1", "true", "yes", "on")


@app.get(
    "/finastra/b2b/collaterals",
    tags=["finastra"],
    summary="List Finastra collaterals (B2B)",
)
def list_finastra_collaterals(
    top: int = Query(
        10,
        ge=1,
        le=100,
        description="Maximum number of items to return (1-100)",
    ),
    startingIndex: int = Query(
        0,
        ge=0,
        description="Zero-based index to start listing from",
    ),
    _: None = Depends(require_token),
):
    """Proxy to Finastra Collaterals list endpoint with simple pagination.

    - Product: B2B `total-lending/collaterals`
    - Requires valid Finastra client credentials.
    """
    if not _feature_enabled():
        raise HTTPException(status_code=404, detail="feature_disabled")
    t0 = time.perf_counter()
    try:
        client = _fin_client()
        data = client.list_collaterals(startingIndex=startingIndex, pageSize=top)
        # structured success log
        logging.getLogger(__name__).info(
            "fin_collaterals_success",
            extra={
                "endpoint": "/finastra/b2b/collaterals",
                "status": 200,
                "elapsed_ms": int((time.perf_counter() - t0) * 1000),
                "tenant": FINASTRA_TENANT,
                "product": os.getenv("FINASTRA_PRODUCT_COLLATERAL", "total-lending/collaterals/b2b/v2"),
            },
        )
        return data
    except Exception as e:
        # If upstream raised an HTTPError, surface status when possible
        status = 502
        try:
            import requests
            if isinstance(e, requests.HTTPError) and e.response is not None:
                # Log Finastra correlation headers for troubleshooting
                try:
                    logging.getLogger(__name__).error(
                        "fin_collaterals_error",
                        extra={
                            "endpoint": "/finastra/b2b/collaterals",
                            "status": e.response.status_code,
                            "elapsed_ms": int((time.perf_counter() - t0) * 1000),
                            "ff-trace-id": e.response.headers.get("ff-trace-id"),
                            "activityId": e.response.headers.get("activityId"),
                        },
                    )
                except Exception:
                    pass
                status = e.response.status_code
                detail = e.response.text
                raise HTTPException(status_code=status, detail=detail)
        except Exception:
            pass
        logging.getLogger(__name__).error(
            "fin_collaterals_error",
            extra={
                "endpoint": "/finastra/b2b/collaterals",
                "status": status,
                "elapsed_ms": int((time.perf_counter() - t0) * 1000),
                "tenant": FINASTRA_TENANT,
                "product": os.getenv("FINASTRA_PRODUCT_COLLATERAL", "total-lending/collaterals/b2b/v2"),
            },
        )
        raise HTTPException(status_code=status, detail=str(e))


@app.get(
    "/finastra/b2b/collaterals/{collateral_id}",
    tags=["finastra"],
    summary="Get Finastra collateral by ID (B2B)",
)
def get_finastra_collateral(
    collateral_id: str = Path(
        ..., description="Primary key of the collateral resource in Finastra"
    ),
    _: None = Depends(require_token),
):
    """Proxy to Finastra Collaterals get by ID endpoint.

    - Product: B2B `total-lending/collaterals`
    - Returns 404 if not found in Finastra.
    """
    if not _feature_enabled():
        raise HTTPException(status_code=404, detail="feature_disabled")
    t0 = time.perf_counter()
    try:
        client = _fin_client()
        data = client.get_collateral(collateral_id)
        logging.getLogger(__name__).info(
            "fin_collateral_success",
            extra={
                "endpoint": f"/finastra/b2b/collaterals/{collateral_id}",
                "status": 200,
                "elapsed_ms": int((time.perf_counter() - t0) * 1000),
                "tenant": FINASTRA_TENANT,
                "product": os.getenv("FINASTRA_PRODUCT_COLLATERAL", "total-lending/collaterals/b2b/v2"),
            },
        )
        return data
    except Exception as e:
        status = 502
        try:
            import requests
            if isinstance(e, requests.HTTPError) and e.response is not None:
                # Log Finastra correlation headers for troubleshooting
                try:
                    logging.getLogger(__name__).error(
                        "fin_collateral_error",
                        extra={
                            "endpoint": f"/finastra/b2b/collaterals/{collateral_id}",
                            "status": e.response.status_code,
                            "elapsed_ms": int((time.perf_counter() - t0) * 1000),
                            "ff-trace-id": e.response.headers.get("ff-trace-id"),
                            "activityId": e.response.headers.get("activityId"),
                        },
                    )
                except Exception:
                    pass
                status = e.response.status_code
                detail = e.response.text
                raise HTTPException(status_code=status, detail=detail)
        except Exception:
            pass
        logging.getLogger(__name__).error(
            "fin_collateral_error",
            extra={
                "endpoint": f"/finastra/b2b/collaterals/{collateral_id}",
                "status": status,
                "elapsed_ms": int((time.perf_counter() - t0) * 1000),
                "tenant": FINASTRA_TENANT,
                "product": os.getenv("FINASTRA_PRODUCT_COLLATERAL", "total-lending/collaterals/b2b/v2"),
            },
        )
        raise HTTPException(status_code=status, detail=str(e))


# --------------------------------------------------------------------------------------
# Finastra B2C – Accounts & Balances (stubs behind feature flag)
# --------------------------------------------------------------------------------------


def _b2c_enabled() -> bool:
    return os.getenv("FEATURE_FINASTRA_B2C", "0").lower() in ("1", "true", "yes", "on")


@app.get(
    "/finastra/b2c/accounts",
    tags=["finastra"],
    summary="[Stub] List consumer accounts (B2C)",
)
def list_finastra_accounts_stub(_: None = Depends(require_token)):
    if not _b2c_enabled():
        raise HTTPException(status_code=404, detail="feature_disabled")
    t0 = time.perf_counter()
    # Mocked response for preparation; no live Finastra call yet
    data = {"items": [{"id": "ACC123", "type": "DDA"}]}
    logging.getLogger(__name__).info(
        "fin_b2c_accounts_stub",
        extra={
            "endpoint": "/finastra/b2c/accounts",
            "status": 200,
            "elapsed_ms": int((time.perf_counter() - t0) * 1000),
        },
    )
    return data


@app.get(
    "/finastra/b2c/balances",
    tags=["finastra"],
    summary="[Stub] List consumer balances (B2C)",
)
def list_finastra_balances_stub(_: None = Depends(require_token)):
    if not _b2c_enabled():
        raise HTTPException(status_code=404, detail="feature_disabled")
    t0 = time.perf_counter()
    data = {"items": [{"accountId": "ACC123", "booked": {"amount": 100.0, "currency": "USD"}}]}
    logging.getLogger(__name__).info(
        "fin_b2c_balances_stub",
        extra={
            "endpoint": "/finastra/b2c/balances",
            "status": 200,
            "elapsed_ms": int((time.perf_counter() - t0) * 1000),
        },
    )
    return data


# --------------------------------------------------------------------------------------
# Accounts and Balances sync triggers
# --------------------------------------------------------------------------------------


class _AccountsPayload(BaseModel):
    contexts: list[str] | None = None


@app.post("/sync/accounts", response_model=dict)
async def run_accounts_sync(payload: _AccountsPayload | None = None, _: None = Depends(require_token)):
    ctxs = payload.contexts if payload else None

    async with AccountsClient() as client:
        syncer = FinastraAccountsSyncer(client=client, session_factory=lambda: Session(engine))
        cnt = await syncer.run_once(ctxs)
    return {"ok": True, "processed": cnt}


class _BalancesPayload(BaseModel):
    accountIds: list[str] | None = None


@app.post("/sync/balances", response_model=dict)
async def run_balances_sync(payload: _BalancesPayload | None = None, _: None = Depends(require_token)):
    ids = payload.accountIds if payload else None
    async with BalancesClient() as client:
        syncer = FinastraBalancesSyncer(client=client, session_factory=lambda: Session(engine))
        cnt = await syncer.run_once(ids)
    return {"ok": True, "processed": cnt}


# --------------------------------------------------------------------------------------
# Transactions sync trigger
# --------------------------------------------------------------------------------------

class _TransactionsPayload(BaseModel):
    accountIds: list[str]
    since: str | None = None  # ISO yyyy-mm-dd


@app.post("/sync/transactions", response_model=dict)
async def run_transactions_sync(
    payload: _TransactionsPayload,
    _: None = Depends(require_token),
):
    async with AccountInfoUSClient() as client:
        syncer = FinastraTransactionsSyncer(
            client=client, session_factory=lambda: Session(engine)
        )
        cnt = await syncer.run_once(payload.accountIds, since=payload.since)
    return {"ok": True, "processed": cnt}
