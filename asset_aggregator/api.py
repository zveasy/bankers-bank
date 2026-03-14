"""FastAPI endpoints for the Asset Aggregator."""
from __future__ import annotations
import os
import re
import json
from common.logging import configure_logging
configure_logging(os.getenv("LOG_FORMAT", "json"), service_name="asset_aggregator")

import socket
import time
import logging
from datetime import datetime, timedelta, timezone
from dataclasses import dataclass
from typing import Any, Dict, List, Optional
import asyncio

import httpx
from fastapi import Depends, FastAPI, HTTPException, Query, Path
from common.auth import require_token
from prometheus_client import Counter, Gauge, make_asgi_app
from pydantic import BaseModel
from sqlmodel import Session, select

from treasury_observability.metrics import get_metric, snapshot_latency_seconds

from .db import AssetSnapshot, engine, init_db
from .service import KAFKA_BOOTSTRAP, reconcile_snapshot, run_snapshot_once
from asset_aggregator.syncers.finastra_collateral import CollateralSyncer
from integrations.finastra.collateral_client import CollateralClient
from asset_aggregator.syncers.finastra_accounts import FinastraAccountsSyncer
from asset_aggregator.syncers.finastra_balances import FinastraBalancesSyncer
from integrations.finastra.accounts_client import AccountsClient
from integrations.finastra.balances_client import BalancesClient
from integrations.finastra.http import FinastraHTTP
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

finastra_b2c_context_errors_total = get_metric(
    Counter,
    "finastra_b2c_context_errors_total",
    "Count of B2C account-context failures by endpoint, tenant, context, and status",
    ["endpoint", "tenant", "context", "status"],
)

finastra_b2c_all_contexts_failed_total = get_metric(
    Counter,
    "finastra_b2c_all_contexts_failed_total",
    "Count of B2C requests where all requested contexts failed",
    ["endpoint", "tenant", "status"],
)

finastra_b2c_last_context_error_unixtime = get_metric(
    Gauge,
    "finastra_b2c_last_context_error_unixtime",
    "Unix timestamp of the most recent B2C context-level failure",
    ["endpoint", "tenant"],
)

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
    return _kafka_healthz()


@app.get("/readyz", response_model=dict)
async def readyz():
    # Readiness is used by local/compose healthchecks and should not require JWT/API token.
    return _kafka_healthz()


def _kafka_healthz() -> dict:
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


@dataclass
class _TenantOAuthConfig:
    tenant: str
    base_url: str
    client_id: str | None
    client_secret: str | None
    scope: str
    token_url: str | None


class _AsyncTokenProviderAdapter:
    def __init__(self, provider: ClientCredentialsTokenProvider):
        self._provider = provider

    async def token(self) -> str:
        return self._provider.fetch()

    async def refresh(self) -> str:
        # Force a new token fetch after 401 instead of returning cached token.
        if hasattr(self._provider, "_access_token"):
            setattr(self._provider, "_access_token", None)
        if hasattr(self._provider, "_expires_at"):
            setattr(self._provider, "_expires_at", 0.0)
        return self._provider.fetch()


def _tenant_env_key(tenant: str) -> str:
    key = re.sub(r"[^A-Za-z0-9]+", "_", tenant or "").strip("_").upper()
    return key or "DEFAULT"


def _load_tenant_config_map() -> Dict[str, Dict[str, Any]]:
    raw = os.getenv("FINASTRA_TENANT_CONFIG_JSON", "").strip()
    path = os.getenv("FINASTRA_TENANT_CONFIG_PATH", "").strip()

    payload = raw
    if not payload and path:
        try:
            with open(path, "r", encoding="utf-8") as fh:
                payload = fh.read()
        except OSError:
            return {}

    if not payload:
        return {}
    try:
        data = json.loads(payload)
    except json.JSONDecodeError:
        logging.getLogger(__name__).warning("invalid_finastra_tenant_config_json")
        return {}
    return data if isinstance(data, dict) else {}


def _first_env(tenant_key: str, names: tuple[str, ...]) -> str | None:
    for name in names:
        val = os.getenv(f"{name}__{tenant_key}")
        if val:
            return val
    for name in names:
        val = os.getenv(name)
        if val:
            return val
    return None


def _resolve_tenant_oauth_config(
    tenant_override: str | None = None,
    *,
    scope_default: str = "accounts",
    client_id_vars: tuple[str, ...] = ("FINASTRA_CLIENT_ID",),
    client_secret_vars: tuple[str, ...] = ("FINASTRA_CLIENT_SECRET",),
    base_url_vars: tuple[str, ...] = ("FINASTRA_BASE_URL",),
    scope_vars: tuple[str, ...] = ("FINASTRA_SCOPE",),
    token_url_vars: tuple[str, ...] = ("FINASTRA_TOKEN_URL",),
) -> _TenantOAuthConfig:
    tenant = (tenant_override or os.getenv("FINASTRA_TENANT", FINASTRA_TENANT)).strip() or FINASTRA_TENANT
    tenant_key = _tenant_env_key(tenant)
    cfg_map = _load_tenant_config_map()
    cfg = cfg_map.get(tenant, {}) if isinstance(cfg_map, dict) else {}
    if not isinstance(cfg, dict):
        cfg = {}

    def _cfg_first(*keys: str) -> str | None:
        for k in keys:
            v = cfg.get(k)
            if isinstance(v, str) and v.strip():
                return v.strip()
        return None

    base_url = (
        _cfg_first("base_url", "baseUrl")
        or _first_env(tenant_key, base_url_vars)
        or FINASTRA_BASE_URL
    )
    client_id = _cfg_first("client_id", "clientId") or _first_env(tenant_key, client_id_vars)
    client_secret = _cfg_first("client_secret", "clientSecret") or _first_env(tenant_key, client_secret_vars)
    scope = (
        _cfg_first("scope")
        or _first_env(tenant_key, scope_vars)
        or scope_default
    )
    token_url = _cfg_first("token_url", "tokenUrl") or _first_env(tenant_key, token_url_vars)

    return _TenantOAuthConfig(
        tenant=tenant,
        base_url=base_url.rstrip("/"),
        client_id=client_id,
        client_secret=client_secret,
        scope=scope,
        token_url=token_url,
    )


def _build_client_credentials_provider(cfg: _TenantOAuthConfig) -> ClientCredentialsTokenProvider:
    if not cfg.client_id or not cfg.client_secret:
        raise HTTPException(
            status_code=500,
            detail=f"missing_finastra_credentials_for_tenant:{cfg.tenant}",
        )
    if cfg.token_url:
        return ClientCredentialsTokenProvider(
            token_url=cfg.token_url,
            client_id=cfg.client_id,
            client_secret=cfg.client_secret,
            scope=cfg.scope,
            verify=os.getenv("CA_CERT", True),
        )
    return ClientCredentialsTokenProvider(
        base_url=cfg.base_url,
        tenant=cfg.tenant,
        client_id=cfg.client_id,
        client_secret=cfg.client_secret,
        scope=cfg.scope,
        verify=os.getenv("CA_CERT", True),
    )


def _build_accounts_client(cfg: _TenantOAuthConfig) -> AccountsClient:
    provider = _build_client_credentials_provider(cfg)
    http = FinastraHTTP(
        base_url=cfg.base_url,
        token_provider=_AsyncTokenProviderAdapter(provider),
        product="accounts",
    )
    return AccountsClient(http=http)


def _build_balances_client(cfg: _TenantOAuthConfig) -> BalancesClient:
    provider = _build_client_credentials_provider(cfg)
    http = FinastraHTTP(
        base_url=cfg.base_url,
        token_provider=_AsyncTokenProviderAdapter(provider),
        product="balances",
    )
    return BalancesClient(http=http)


def _b2c_contexts() -> list[str]:
    raw = os.getenv("FINASTRA_B2C_ACCOUNT_CONTEXTS", "MT103,INTERNAL-TRANSFER")
    return [s.strip() for s in raw.split(",") if s.strip()]


def _fin_client(tenant_override: str | None = None) -> FinastraAPIClient:
    """Builds a FinastraAPIClient using env configuration.

    Expects FINASTRA_CLIENT_ID/FINASTRA_CLIENT_SECRET to be present in env
    (see docs/runbooks/finastra.md). Uses default scope "accounts".
    """
    strategy = os.getenv("FINASTRA_TOKEN_STRATEGY", "client_credentials").lower()
    cfg = _resolve_tenant_oauth_config(
        tenant_override=tenant_override,
        scope_default="accounts",
        client_id_vars=("FINASTRA_B2B_CLIENT_ID", "FINASTRA_CLIENT_ID"),
        client_secret_vars=("FINASTRA_B2B_CLIENT_SECRET", "FINASTRA_CLIENT_SECRET"),
        base_url_vars=("FINASTRA_B2B_BASE_URL_COLLATERALS", "FINASTRA_BASE_URL"),
        scope_vars=("FINASTRA_B2B_SCOPE", "FINASTRA_SCOPE"),
        token_url_vars=("FINASTRA_B2B_TOKEN_URL", "FINASTRA_TOKEN_URL"),
    )
    static_bearer = os.getenv(f"FINASTRA_STATIC_BEARER__{_tenant_env_key(cfg.tenant)}") or os.getenv("FINASTRA_STATIC_BEARER")

    # Prefer static bearer when explicitly configured
    if strategy == "static" and static_bearer and static_bearer != "disabled":
        return FinastraAPIClient(
            base_url=cfg.base_url,
            tenant=cfg.tenant,
            token=static_bearer,
        )

    # Fall back to client-credentials
    provider = _build_client_credentials_provider(cfg)
    return FinastraAPIClient(
        base_url=cfg.base_url,
        tenant=cfg.tenant,
        token_provider=provider,
    )


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
    tenant: str | None = Query(
        None,
        description="Optional Finastra tenant override for multi-tenant routing",
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
    resolved_tenant = tenant or FINASTRA_TENANT
    try:
        client = _fin_client(tenant)
        resolved_tenant = client.tenant
        data = client.list_collaterals(startingIndex=startingIndex, pageSize=top)
        # structured success log
        logging.getLogger(__name__).info(
            "fin_collaterals_success",
            extra={
                "endpoint": "/finastra/b2b/collaterals",
                "status": 200,
                "elapsed_ms": int((time.perf_counter() - t0) * 1000),
                "tenant": resolved_tenant,
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
                "tenant": resolved_tenant,
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
    tenant: str | None = Query(
        None,
        description="Optional Finastra tenant override for multi-tenant routing",
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
    resolved_tenant = tenant or FINASTRA_TENANT
    try:
        client = _fin_client(tenant)
        resolved_tenant = client.tenant
        data = client.get_collateral(collateral_id)
        logging.getLogger(__name__).info(
            "fin_collateral_success",
            extra={
                "endpoint": f"/finastra/b2b/collaterals/{collateral_id}",
                "status": 200,
                "elapsed_ms": int((time.perf_counter() - t0) * 1000),
                "tenant": resolved_tenant,
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
                "tenant": resolved_tenant,
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
    summary="List consumer accounts (B2C)",
)
async def list_finastra_accounts(
    contexts: list[str] | None = Query(
        None,
        description="Optional repeated query param, e.g. ?contexts=MT103&contexts=INTERNAL-TRANSFER",
    ),
    limit: int = Query(50, ge=1, le=100),
    tenant: str | None = Query(
        None,
        description="Optional Finastra tenant override for multi-tenant routing",
    ),
    _: None = Depends(require_token),
):
    if not _b2c_enabled():
        raise HTTPException(status_code=404, detail="feature_disabled")
    t0 = time.perf_counter()
    cfg = _resolve_tenant_oauth_config(
        tenant_override=tenant,
        scope_default="accounts",
        client_id_vars=("FINASTRA_B2C_CLIENT_ID", "FINASTRA_CLIENT_ID"),
        client_secret_vars=("FINASTRA_B2C_CLIENT_SECRET", "FINASTRA_CLIENT_SECRET"),
        base_url_vars=("FINASTRA_B2C_BASE_URL", "FINASTRA_BASE_URL"),
        scope_vars=("FINASTRA_B2C_SCOPE", "FINASTRA_SCOPE"),
        token_url_vars=("FINASTRA_B2C_TOKEN_URL", "FINASTRA_TOKEN_URL"),
    )
    use_contexts = contexts or _b2c_contexts()
    try:
        items: list[dict] = []
        context_errors: list[dict[str, Any]] = []
        async with _build_accounts_client(cfg) as client:
            for ctx in use_contexts:
                try:
                    async for page in client.list_accounts(ctx, limit=limit):
                        items.extend(acc.raw for acc in page)
                except httpx.HTTPStatusError as e:
                    status_code = e.response.status_code if e.response is not None else 502
                    finastra_b2c_context_errors_total.labels(
                        endpoint="/finastra/b2c/accounts",
                        tenant=cfg.tenant,
                        context=ctx,
                        status=str(status_code),
                    ).inc()
                    finastra_b2c_last_context_error_unixtime.labels(
                        endpoint="/finastra/b2c/accounts",
                        tenant=cfg.tenant,
                    ).set_to_current_time()
                    context_errors.append(
                        {
                            "context": ctx,
                            "status": status_code,
                            "detail": e.response.text if e.response is not None else str(e),
                        }
                    )
                    continue
        if not items and context_errors:
            first = context_errors[0]
            finastra_b2c_all_contexts_failed_total.labels(
                endpoint="/finastra/b2c/accounts",
                tenant=cfg.tenant,
                status=str(first["status"]),
            ).inc()
            raise HTTPException(
                status_code=first["status"],
                detail={"error": "all_contexts_failed", "context_errors": context_errors},
            )
        data = {
            "items": items,
            "meta": {
                "tenant": cfg.tenant,
                "contexts": use_contexts,
                "context_errors": context_errors,
            },
        }
        logging.getLogger(__name__).info(
            "fin_b2c_accounts_success",
            extra={
                "endpoint": "/finastra/b2c/accounts",
                "status": 200,
                "elapsed_ms": int((time.perf_counter() - t0) * 1000),
                "tenant": cfg.tenant,
                "context_errors_count": len(context_errors),
            },
        )
        return data
    except httpx.HTTPStatusError as e:
        status = e.response.status_code if e.response is not None else 502
        detail = e.response.text if e.response is not None else str(e)
        raise HTTPException(status_code=status, detail=detail)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=502, detail=str(e))


@app.get(
    "/finastra/b2c/balances",
    tags=["finastra"],
    summary="List consumer balances (B2C)",
)
async def list_finastra_balances(
    accountId: list[str] | None = Query(
        None,
        description="Optional repeated query param, e.g. ?accountId=acc-1&accountId=acc-2",
    ),
    contexts: list[str] | None = Query(
        None,
        description="Used only when accountId is omitted; fetches account IDs from these contexts",
    ),
    limit: int = Query(50, ge=1, le=100),
    tenant: str | None = Query(
        None,
        description="Optional Finastra tenant override for multi-tenant routing",
    ),
    _: None = Depends(require_token),
):
    if not _b2c_enabled():
        raise HTTPException(status_code=404, detail="feature_disabled")
    t0 = time.perf_counter()
    cfg = _resolve_tenant_oauth_config(
        tenant_override=tenant,
        scope_default="accounts",
        client_id_vars=("FINASTRA_B2C_CLIENT_ID", "FINASTRA_CLIENT_ID"),
        client_secret_vars=("FINASTRA_B2C_CLIENT_SECRET", "FINASTRA_CLIENT_SECRET"),
        base_url_vars=("FINASTRA_B2C_BASE_URL", "FINASTRA_BASE_URL"),
        scope_vars=("FINASTRA_B2C_SCOPE", "FINASTRA_SCOPE"),
        token_url_vars=("FINASTRA_B2C_TOKEN_URL", "FINASTRA_TOKEN_URL"),
    )
    use_account_ids = list(accountId or [])
    use_contexts = contexts or _b2c_contexts()
    try:
        context_errors: list[dict[str, Any]] = []
        if not use_account_ids:
            async with _build_accounts_client(cfg) as account_client:
                for ctx in use_contexts:
                    try:
                        async for page in account_client.list_accounts(ctx, limit=limit):
                            use_account_ids.extend(
                                acc.external_id for acc in page if acc.external_id
                            )
                    except httpx.HTTPStatusError as e:
                        status_code = e.response.status_code if e.response is not None else 502
                        finastra_b2c_context_errors_total.labels(
                            endpoint="/finastra/b2c/balances",
                            tenant=cfg.tenant,
                            context=ctx,
                            status=str(status_code),
                        ).inc()
                        finastra_b2c_last_context_error_unixtime.labels(
                            endpoint="/finastra/b2c/balances",
                            tenant=cfg.tenant,
                        ).set_to_current_time()
                        context_errors.append(
                            {
                                "context": ctx,
                                "status": status_code,
                                "detail": e.response.text if e.response is not None else str(e),
                            }
                        )
                        continue
            # de-duplicate while preserving order
            use_account_ids = list(dict.fromkeys(use_account_ids))
            if not use_account_ids and context_errors:
                first = context_errors[0]
                finastra_b2c_all_contexts_failed_total.labels(
                    endpoint="/finastra/b2c/balances",
                    tenant=cfg.tenant,
                    status=str(first["status"]),
                ).inc()
                raise HTTPException(
                    status_code=first["status"],
                    detail={"error": "all_contexts_failed", "context_errors": context_errors},
                )
        else:
            context_errors = []

        items: list[dict] = []
        if use_account_ids:
            async with _build_balances_client(cfg) as balance_client:
                async for balance_page in balance_client.list_all_balances(use_account_ids):
                    items.extend(dict(b) for b in balance_page)

        data = {
            "items": items,
            "meta": {
                "tenant": cfg.tenant,
                "accountIds": use_account_ids,
                "contexts": use_contexts,
                "context_errors": context_errors,
            },
        }
        logging.getLogger(__name__).info(
            "fin_b2c_balances_success",
            extra={
                "endpoint": "/finastra/b2c/balances",
                "status": 200,
                "elapsed_ms": int((time.perf_counter() - t0) * 1000),
                "tenant": cfg.tenant,
                "accounts_count": len(use_account_ids),
                "context_errors_count": len(context_errors),
            },
        )
        return data
    except httpx.HTTPStatusError as e:
        status = e.response.status_code if e.response is not None else 502
        detail = e.response.text if e.response is not None else str(e)
        raise HTTPException(status_code=status, detail=detail)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=502, detail=str(e))


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
