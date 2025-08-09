import os

import redis
from fastapi import Depends, FastAPI, HTTPException
from prometheus_client import make_asgi_app
from sqlmodel import Session

from .db import get_cash, get_session, init_db

# --- Metrics (safe fallback if treasury_observability is missing)
try:
    # mounting /metrics via ASGI in this service; the helper module should NOT start its own server
    from treasury_observability.metrics import \
        treas_ltv_ratio as ltv_gauge  # type: ignore
except Exception:  # pragma: no cover

    class _NoopGauge:
        def labels(self, *_, **__):
            return self

        def set(self, *_, **__):
            ...

    ltv_gauge = _NoopGauge()  # type: ignore

app = FastAPI()
init_db()

REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")
redis_client = redis.Redis.from_url(REDIS_URL)

# Expose Prometheus metrics on /metrics
app.mount("/metrics", make_asgi_app())


@app.get("/healthz")
def healthz():
    """Simple Redis liveness probe used by the container healthcheck."""
    try:
        redis_client.ping()
        return {"ok": True}
    except Exception as exc:
        raise HTTPException(status_code=503, detail=f"redis:{exc}")


@app.get("/investable-cash")
def investable_cash(bank_id: str, session: Session = Depends(get_session)):
    """
    Return investable cash for a bank.
    - Prefer Redis cache; fall back to the quant DB.
    - Also update a demo LTV gauge so it shows up in Prometheus.
    """
    val = redis_client.get(f"cash_available:{bank_id}")
    if val is not None:
        cash = float(val)  # bytes -> float
    else:
        db_cash = get_cash(session, bank_id)
        if db_cash is None:
            raise HTTPException(status_code=404, detail="bank not found")
        cash = db_cash

    # Demo: publish an LTV gauge so the time series exists.
    # Replace this with a real LTV computation when available.
    try:
        demo_ltv = 0.0
        ltv_gauge.labels(bank_id=bank_id).set(demo_ltv)
    except Exception:
        pass

    return {"cash": cash}
