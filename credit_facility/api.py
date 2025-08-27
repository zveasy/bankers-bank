"""FastAPI router exposing credit actions (Sprint 7 / PR-2)."""
from __future__ import annotations
import os
from common.logging import configure_logging
configure_logging(os.getenv("LOG_FORMAT", "json"), service_name="credit_facility")

import time
from datetime import datetime
from typing import Dict, List, Optional

from fastapi import APIRouter, Depends, FastAPI, Header, HTTPException, status
from common.auth import require_token
from prometheus_client import make_asgi_app
from pydantic import BaseModel, Field
from sqlmodel import Session, select
from sqlmodel import Session as _AuditSession  # audit
from common.audit import log_event, get_engine as _audit_engine  # audit

from asset_aggregator.db import get_session  # shared session helper
from credit_facility.models import CreditDraw, CreditRepayment
from credit_facility.providers.base import CreditProvider
from credit_facility.providers.mock_finastra import MockFinastra
from credit_facility.service import CreditFacilityService
from treasury_observability.metrics import (credit_actions_total,
                                            credit_provider_latency_seconds)
from treasury_orchestrator.credit_db import log_audit, AuditAction

# ---------------------------------------------------------------------------
# Dependency injection helpers
# ---------------------------------------------------------------------------


def get_provider() -> CreditProvider:  # pragma: no cover – simple default
    """Select provider adapter via env in future; default to mock."""
    return MockFinastra()


# ---------------------------------------------------------------------------
# Pydantic schemas
# ---------------------------------------------------------------------------


class ActionRequest(BaseModel):
    bank_id: str = Field(..., min_length=1)
    amount: float = Field(..., gt=0)
    currency: str = Field(default="USD", min_length=3, max_length=3)
    client_txn_id: Optional[str] = None


class ActionResponse(BaseModel):
    id: int
    status: str
    provider_ref: Optional[str] = None
    outstanding: float


class StatusResponse(BaseModel):
    bank_id: str
    cap: float
    buffer: float
    outstanding: float
    available: float
    last_actions: List[Dict]


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _recompute_outstanding_gauge(svc: CreditFacilityService, bank_id: str) -> float:
    """Recompute service metrics and return fresh outstanding amount."""
    available = svc.capacity(bank_id)  # updates gauges internally
    # access private for gauge update; acceptable in same subsystem
    outstanding = svc._outstanding(bank_id)  # type: ignore[attr-defined]
    return outstanding


async def _call_provider(
    action: str,
    provider: CreditProvider,
    bank_id: str,
    amount: float,
    currency: str,
    idem: str,
) -> str:
    """Wrap provider call with latency histogram."""
    t0 = time.perf_counter()
    try:
        if action == "draw":
            res = await provider.send_draw(bank_id, amount, currency, idem)
        else:
            res = await provider.send_repay(bank_id, amount, currency, idem)
        return res.get("provider_ref", "")
    finally:
        credit_provider_latency_seconds.labels(
            action=action, provider=provider.__class__.__name__
        ).observe(time.perf_counter() - t0)


# ---------------------------------------------------------------------------
# Router definition
# ---------------------------------------------------------------------------

router = APIRouter(prefix="/api/credit/v1", tags=["credit"])


def create_app() -> FastAPI:  # pragma: no cover
    """Factory used by tests and __main__ entrypoint."""
    app = FastAPI(title="Credit Facility Service")
    app.include_router(router)
    app.mount("/metrics", make_asgi_app())
    return app


@router.post(
    "/draw", response_model=ActionResponse, status_code=status.HTTP_201_CREATED
)
async def draw_funds(
    req: ActionRequest,
    idempotency_key: str = Header(..., alias="Idempotency-Key"),
    session: Session = Depends(get_session),
    provider: CreditProvider = Depends(get_provider),
    _: None = Depends(require_token),
):
    svc = CreditFacilityService(session)

    # Idempotency check
    prior: CreditDraw | None = session.exec(
        select(CreditDraw).where(
            CreditDraw.bank_id == req.bank_id,
            CreditDraw.idempotency_key == idempotency_key,
        )
    ).first()
    if prior:
        if prior.status == "POSTED":
            credit_actions_total.labels(
                action="draw",
                outcome="idempotent",
                provider=provider.__class__.__name__,
            ).inc()
            # --- Audit log ---
            with _AuditSession(_audit_engine()) as _aud_sess:
                log_event(
                    session=_aud_sess,
                    service="credit_facility",
                    action="CREDIT_DRAW",
                    actor=req.bank_id,
                    details={
                        "amount": req.amount,
                        "currency": req.currency,
                        "status": prior.status,
                    },
                )
            # recompute outstanding and return idempotent response
            outstanding = _recompute_outstanding_gauge(svc, req.bank_id)
            return ActionResponse(
                id=prior.id,
                status=prior.status,
                provider_ref=prior.provider_ref,
                outstanding=outstanding,
            )
        raise HTTPException(status_code=409, detail="idempotency_key_conflict")

    # Capacity guard
    available = svc.capacity(req.bank_id)
    if req.amount > available:
        credit_actions_total.labels(
            action="draw", outcome="invalid", provider=provider.__class__.__name__
        ).inc()
        raise HTTPException(status_code=400, detail="insufficient_capacity")

    # Persist PENDING row
    row = CreditDraw(
        bank_id=req.bank_id,
        amount=req.amount,
        currency=req.currency,
        status="PENDING",
        idempotency_key=idempotency_key,
        provider_ref=None,
        created_at=datetime.utcnow(),
    )
    session.add(row)
    session.commit()
    session.refresh(row)

    # Provider call
    try:
        provider_ref = await _call_provider(
            "draw", provider, req.bank_id, req.amount, req.currency, idempotency_key
        )
        row.status = "POSTED"
        row.provider_ref = provider_ref
        session.add(row)
        session.commit()
        credit_actions_total.labels(
            action="draw", outcome="success", provider=provider.__class__.__name__
        ).inc()
    except Exception as exc:
        row.status = "FAILED"
        session.add(row)
        session.commit()
        credit_actions_total.labels(
            action="draw", outcome="fail", provider=provider.__class__.__name__
        ).inc()
        # --- Audit log (failure) ---
        with _AuditSession(_audit_engine()) as _aud_sess:
            log_event(
                session=_aud_sess,
                service="credit_facility",
                action="CREDIT_DRAW_FAILED",
                actor=req.bank_id,
                details={
                    "amount": req.amount,
                    "currency": req.currency,
                    "error": str(exc),
                    "status": row.status,
                },
            )
        raise HTTPException(status_code=502, detail=f"provider_error: {exc}")

    # --- Audit log ---
    with _AuditSession(_audit_engine()) as _aud_sess:
        log_event(
                session=_aud_sess,
            service="credit_facility",
            action="CREDIT_DRAW",
            actor=req.bank_id,
            details={
                "amount": req.amount,
                "currency": req.currency,
                "status": row.status,
            },
        )

    outstanding = _recompute_outstanding_gauge(svc, req.bank_id)
    return ActionResponse(
        id=row.id,
        status=row.status,
        provider_ref=row.provider_ref,
        outstanding=outstanding,
    )


@router.post(
    "/repay", response_model=ActionResponse, status_code=status.HTTP_201_CREATED
)
async def repay_funds(
    req: ActionRequest,
    idempotency_key: str = Header(..., alias="Idempotency-Key"),
    session: Session = Depends(get_session),
    provider: CreditProvider = Depends(get_provider),
    _: None = Depends(require_token),
):
    svc = CreditFacilityService(session)

    prior: CreditRepayment | None = session.exec(
        select(CreditRepayment).where(
            CreditRepayment.bank_id == req.bank_id,
            CreditRepayment.idempotency_key == idempotency_key,
        )
    ).first()
    if prior:
        if prior.status == "POSTED":
            credit_actions_total.labels(
                action="repay",
                outcome="idempotent",
                provider=provider.__class__.__name__,
            ).inc()
            # --- Audit log ---
            with _AuditSession(_audit_engine()) as _aud_sess:
                log_event(
                    session=_aud_sess,
                    service="credit_facility",
                    action="CREDIT_REPAY",
                    actor=req.bank_id,
                    details={
                        "amount": req.amount,
                        "currency": req.currency,
                        "status": prior.status,
                    },
                )
            # recompute outstanding and return idempotent response
            outstanding = _recompute_outstanding_gauge(svc, req.bank_id)
            return ActionResponse(
                id=prior.id,
                status=prior.status,
                provider_ref=prior.provider_ref,
                outstanding=outstanding,
            )
        raise HTTPException(status_code=409, detail="idempotency_key_conflict")

    row = CreditRepayment(
        bank_id=req.bank_id,
        amount=req.amount,
        currency=req.currency,
        status="PENDING",
        idempotency_key=idempotency_key,
        provider_ref=None,
        created_at=datetime.utcnow(),
    )
    session.add(row)
    session.commit()
    session.refresh(row)

    try:
        provider_ref = await _call_provider(
            "repay", provider, req.bank_id, req.amount, req.currency, idempotency_key
        )
        row.status = "POSTED"
        row.provider_ref = provider_ref
        session.add(row)
        session.commit()
        credit_actions_total.labels(
            action="repay", outcome="success", provider=provider.__class__.__name__
        ).inc()
    except Exception as exc:
        row.status = "FAILED"
        session.add(row)
        session.commit()
        credit_actions_total.labels(
            action="repay", outcome="fail", provider=provider.__class__.__name__
        ).inc()
        # --- Audit log (failure) ---
        with _AuditSession(_audit_engine()) as _aud_sess:
            log_event(
                session=_aud_sess,
                service="credit_facility",
                action="CREDIT_REPAY_FAILED",
                actor=req.bank_id,
                details={
                    "amount": req.amount,
                    "currency": req.currency,
                    "error": str(exc),
                    "status": row.status,
                },
            )
        raise HTTPException(status_code=502, detail=f"provider_error: {exc}")

    # --- Audit log ---
    with _AuditSession(_audit_engine()) as _aud_sess:
        log_event(
                session=_aud_sess,
            service="credit_facility",
            action="CREDIT_REPAY",
            actor=req.bank_id,
            details={
                "amount": req.amount,
                "currency": req.currency,
                "status": row.status,
            },
        )

    outstanding = _recompute_outstanding_gauge(svc, req.bank_id)
    return ActionResponse(
        id=row.id,
        status=row.status,
        provider_ref=row.provider_ref,
        outstanding=outstanding,
    )


@router.get("/{bank_id}/status", response_model=StatusResponse)
async def facility_status(
    bank_id: str, session: Session = Depends(get_session), _: None = Depends(require_token)
):
    svc = CreditFacilityService(session)
    available = svc.capacity(bank_id)
    outstanding = svc._outstanding(bank_id)  # type: ignore[attr-defined]

    # last actions (max 5 total)
    draws = session.exec(
        select(CreditDraw)
        .where(CreditDraw.bank_id == bank_id)
        .order_by(CreditDraw.created_at.desc())
        .limit(5)
    ).all()
    repays = session.exec(
        select(CreditRepayment)
        .where(CreditRepayment.bank_id == bank_id)
        .order_by(CreditRepayment.created_at.desc())
        .limit(5)
    ).all()

    merged = [
        {"type": "draw", "amount": d.amount, "currency": d.currency, "status": d.status, "ts": d.created_at.isoformat()}  # type: ignore[attr-defined]
        for d in draws
    ] + [
        {"type": "repay", "amount": r.amount, "currency": r.currency, "status": r.status, "ts": r.created_at.isoformat()}  # type: ignore[attr-defined]
        for r in repays
    ]
    merged.sort(key=lambda x: x["ts"], reverse=True)
    merged = merged[:5]

    return StatusResponse(
        bank_id=bank_id,
        cap=available + outstanding,
        buffer=0.0,
        outstanding=outstanding,
        available=available,
        last_actions=merged,
    )


# ---------------------------------------------------------------------------
# ASGI app factory
# ---------------------------------------------------------------------------


def create_app() -> FastAPI:  # pragma: no cover
    app = FastAPI(title="Credit Facility API")
    app.include_router(router)
    # ensure /metrics mounted exactly once
    if not any(r.path == "/metrics" for r in app.routes):
        app.mount("/metrics", make_asgi_app())

    @app.get("/healthz", tags=["health"])
    async def healthz(_: None = Depends(require_token)):
        return {"ok": True}

    # ensure tables exist on boot (safe idempotent)
    @app.on_event("startup")
    def _startup_init_db() -> None:  # pragma: no cover
        from asset_aggregator.db import (  # lazy import to avoid cycles
            SQLModel, engine)

        SQLModel.metadata.create_all(engine)

    return app


app = create_app()
