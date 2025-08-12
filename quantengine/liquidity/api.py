"""FastAPI router exposing Liquidity evaluation and Quant bridge publish.

All logic is side-effect free except Prometheus metrics.
The module can be imported standalone for testing (``create_app``) or
its router can be included by an outer application like ``quantengine.main``.
"""
from __future__ import annotations

import os
import time
from datetime import datetime, timezone
from typing import List, Optional

from fastapi import APIRouter, Depends, FastAPI, HTTPException
from pydantic import BaseModel, Field, validator

from ..bridge.quant_bridge import publish_cash_position
from .policy import LiquidityPolicy, compute_buffer
from .policy import evaluate as policy_evaluate

# Prometheus metrics (already registered globally)
try:
    from treasury_observability.metrics import (liquidity_buffer_usd,
                                                policy_violations_total,
                                                quant_publish_latency_seconds,
                                                quant_publish_total)
except Exception:  # pragma: no cover – fallback stubs for unit tests

    class _NoopMetric:  # noqa: D401 – simple stub
        def labels(self, *_, **__):
            return self

        def inc(self, *_: int, **__):
            ...

        def set(self, *_: float, **__):
            ...

        def observe(self, *_: float, **__):
            ...

    liquidity_buffer_usd = policy_violations_total = quant_publish_total = _NoopMetric()  # type: ignore
    quant_publish_latency_seconds = _NoopMetric()  # type: ignore


router = APIRouter()

# ---------------------------------------------------------------------------
# Pydantic schemas
# ---------------------------------------------------------------------------


class PolicyModel(BaseModel):
    min_cash_bps: int = Field(0, ge=0, le=10_000)
    max_draw_bps: int = Field(10_000, ge=0, le=10_000)
    settlement_calendar: List[str] = Field(default_factory=list)


class EvaluateRequest(BaseModel):
    bank_id: str
    available_cash_usd: float = Field(gt=0)
    requested_draw_usd: float = Field(0, ge=0)
    asof_ts: Optional[str] = None
    policy: PolicyModel

    @validator("asof_ts", pre=True, always=True)
    def _default_ts(cls, v):  # noqa: D401
        return v or datetime.now(timezone.utc).isoformat()

    def as_policy(self) -> LiquidityPolicy:
        return LiquidityPolicy(
            min_cash_bps=self.policy.min_cash_bps,
            max_draw_bps=self.policy.max_draw_bps,
            settlement_calendar=set(self.policy.settlement_calendar),
        )


class EvaluateResponse(BaseModel):
    ok: bool
    reasons: List[str]
    allowed_draw_usd: float
    buffer_usd: float


# --- publish ----------------------------------------------------------------


class PublishRequest(BaseModel):
    bank_id: str
    asof_ts: str
    available_cash_usd: float = Field(gt=0)
    reserved_buffer_usd: float = Field(0, ge=0)
    notes: Optional[str] = None


class PublishResponse(BaseModel):
    ok: bool
    dry_run: bool
    key: Optional[str] = None


# ---------------------------------------------------------------------------
# Endpoint impls
# ---------------------------------------------------------------------------


@router.post("/liquidity/evaluate", response_model=EvaluateResponse)
def liquidity_evaluate(req: EvaluateRequest):
    policy = req.as_policy()

    # asof date (YYYY-MM-DD) for holiday rule
    try:
        asof_date = datetime.fromisoformat(req.asof_ts).date()  # type: ignore[arg-type]
    except Exception:
        raise HTTPException(status_code=400, detail="invalid asof_ts ISO format")

    result = policy_evaluate(
        policy,
        available_cash_usd=req.available_cash_usd,
        requested_draw_usd=req.requested_draw_usd,
        asof=asof_date,
    )

    # Update buffer gauge for every call (irrespective of ok)
    buffer_usd = compute_buffer(req.available_cash_usd, policy.min_cash_bps)
    try:
        liquidity_buffer_usd.labels(bank_id=req.bank_id).set(buffer_usd)
    except Exception:
        pass

    # Counters for violations
    if not result["ok"]:
        for reason in result["reasons"]:
            try:
                policy_violations_total.labels(bank_id=req.bank_id, rule=reason).inc()
            except Exception:
                pass

    return {
        **result,
        "buffer_usd": buffer_usd,
    }


@router.post("/bridge/publish", response_model=PublishResponse)
def bridge_publish(req: PublishRequest):
    dry_run = os.getenv("QUANT_DRY_RUN", "1") != "0"

    start = time.perf_counter()
    try:
        payload = {
            "bank_id": req.bank_id,
            "asof_ts": req.asof_ts,
            "available_cash_usd": req.available_cash_usd,
            "reserved_buffer_usd": req.reserved_buffer_usd,
            "notes": req.notes,
        }
        res = publish_cash_position(
            payload,
            dry_run=dry_run,
        )
        key = res.get("key")
        result_label = "ok" if res.get("ok") else "error"
        ok = res.get("ok", False)
    except Exception as exc:  # pragma: no cover – shouldn't happen in offline tests
        key = None
        ok = False
        result_label = "error"
        # Bubble up internal error for FastAPI default handler
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    finally:
        latency = time.perf_counter() - start
        try:
            quant_publish_latency_seconds.labels(path="/bridge/publish").observe(
                latency
            )
            quant_publish_total.labels(result=result_label).inc()
        except Exception:
            pass

    return {
        "ok": ok,
        "dry_run": dry_run,
        "key": key,
    }


# ---------------------------------------------------------------------------
# Optional helper to create a standalone app for tests
# ---------------------------------------------------------------------------


def create_app() -> FastAPI:  # pragma: no cover – used by tests when main unavailable
    from fastapi import FastAPI

    _app = FastAPI()
    # Mount default /metrics server exactly once
    try:
        from prometheus_client import make_asgi_app

        _app.mount("/metrics", make_asgi_app())
    except Exception:
        pass

    _app.include_router(router)
    return _app


__all__ = [
    "router",
    "create_app",
]
