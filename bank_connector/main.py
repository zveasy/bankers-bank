from __future__ import annotations

import asyncio
import os
import random
import time
import uuid
from collections import deque
from typing import Deque, Optional, TypedDict

import httpx
from fastapi import Depends, FastAPI, Header, HTTPException, Request
from fastapi.responses import JSONResponse
from prometheus_client import make_asgi_app
from sqlmodel import Session, select

from bank_connector.iso20022 import build_pain001, parse_pain002, PaymentStatus
from treasury_observability.metrics import (
    rails_dlq_depth,
    rails_end_to_end_seconds,
    rails_post_total,
)

from .db import SweepOrder, get_session, init_db
from .models import PaymentStatusResponse, SweepOrderRequest

app = FastAPI()
init_db()

# expose metrics once
app.mount("/metrics", make_asgi_app())

# ---------------------------------------------------------------------------
# Env flags
# ---------------------------------------------------------------------------

def _env_bool(name: str, default: str = "0") -> bool:
    return os.getenv(name, default).lower() in {"1", "true", "yes", "on", "y"}


# These are read at runtime so tests can monkeypatch env per request

def _rails_enabled() -> bool:
    return _env_bool("BANK_RAILS_ENABLED", "0")


def _rails_url() -> str:
    return os.getenv("BANK_RAILS_URL", os.getenv("BANK_API_URL", "http://localhost:8000"))


# ---------------------------------------------------------------------------
# In-process DLQ
# ---------------------------------------------------------------------------

class _DlqItem(TypedDict):
    bank_id: str
    xml: bytes
    attempt: int
    idem_key: str


_DLQ: Deque[_DlqItem] = deque()
_worker_started = False


async def _backoff_sleep(attempt: int) -> None:
    base = min(5.0, 0.1 * (2 ** attempt))  # cap at 5s
    delay = base * (0.8 + 0.4 * random.random())
    await asyncio.sleep(delay)


async def _dlq_worker() -> None:
    while True:
        if not _DLQ:
            await asyncio.sleep(0.5)
            continue

        rails_dlq_depth.set(len(_DLQ))
        item = _DLQ[0]  # peek
        try:
            start = time.perf_counter()
            async with httpx.AsyncClient(timeout=5.0) as client:
                r = await client.post(
                    _rails_url(),
                    content=item["xml"],
                    headers={
                        "Content-Type": "application/xml",
                        "Idempotency-Key": item["idem_key"],
                    },
                )
            duration = time.perf_counter() - start
            result = "ok" if 200 <= r.status_code < 300 else "err"
            rails_post_total.labels(
                result=result,
                http_status=str(r.status_code),
                endpoint="sweep",
                bank_id=item["bank_id"],
            ).inc()
            rails_end_to_end_seconds.labels(endpoint="sweep", bank_id=item["bank_id"]).observe(duration)
            if result == "ok":
                _DLQ.popleft()
            else:
                raise RuntimeError("rails non-2xx")
        except Exception:
            item["attempt"] += 1
            await _backoff_sleep(item["attempt"])
            # item stays at front for next cycle


@app.on_event("startup")
async def _start_worker() -> None:
    global _worker_started
    if not _worker_started:
        _worker_started = True
        asyncio.create_task(_dlq_worker())


@app.get("/healthz")
async def healthz():
    return {"ok": True}


# ---------------------------------------------------------------------------
# /sweep-order
# ---------------------------------------------------------------------------


@app.post("/sweep-order")
async def create_sweep_order(
    payload: SweepOrderRequest,
    session: Session = Depends(get_session),
    idempotency_key: Optional[str] = Header(default=None, alias="Idempotency-Key"),
):
    idem = idempotency_key or str(uuid.uuid4())
    # persist (idempotent upsert by order_id)
    existing: SweepOrder | None = session.exec(select(SweepOrder).where(SweepOrder.order_id == payload.order_id)).first()
    if existing:
        return {"id": existing.id, "queued": False}

    order = SweepOrder(
        order_id=payload.order_id,
        amount=payload.amount,
        currency=payload.currency,
        debtor=payload.debtor,
        creditor=payload.creditor,
        status="PENDING",
    )
    session.add(order)
    session.commit()
    session.refresh(order)

    # build XML
    exec_ts = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())

    class _Clock:
        @staticmethod
        def now_iso() -> str:  # noqa: D401
            return exec_ts

    class _UuidF:
        @staticmethod
        def new() -> str:  # noqa: D401
            return str(uuid.uuid4())

    xml_str = build_pain001(
        order_id=payload.order_id,
        amount=payload.amount,
        currency=payload.currency,
        debtor=payload.debtor,
        creditor=payload.creditor,
        execution_ts=exec_ts,
        clock=_Clock(),
        uuidf=_UuidF(),
    )
    xml_bytes = xml_str.encode()

    if not _rails_enabled():
        rails_post_total.labels(result="ok", http_status="disabled", endpoint="sweep", bank_id=payload.debtor).inc()
        order.status = "SENT"
        session.add(order)
        session.commit()
        return {"id": order.id, "queued": False}

    try:
        start = time.perf_counter()
        async with httpx.AsyncClient(timeout=5.0) as client:
            r = await client.post(
                _rails_url(),
                content=xml_bytes,
                headers={"Content-Type": "application/xml", "Idempotency-Key": idem},
            )
        duration = time.perf_counter() - start
        result = "ok" if 200 <= r.status_code < 300 else "err"
        rails_post_total.labels(result=result, http_status=str(r.status_code), endpoint="sweep", bank_id=payload.debtor).inc()
        rails_end_to_end_seconds.labels(endpoint="sweep", bank_id=payload.debtor).observe(duration)
        if result == "ok":
            order.status = "SENT"
            session.add(order)
            session.commit()
            return {"id": order.id, "queued": False}
        raise RuntimeError("non-2xx")
    except Exception:
        _DLQ.append({"bank_id": payload.debtor, "xml": xml_bytes, "attempt": 0, "idem_key": idem})
        rails_dlq_depth.set(len(_DLQ))
        order.status = "QUEUED"
        session.add(order)
        session.commit()
        return JSONResponse({"id": order.id, "queued": True}, status_code=202)


# ---------------------------------------------------------------------------
# /payment-status
# ---------------------------------------------------------------------------


@app.post("/payment-status")
async def payment_status(
    request: Request,
    session: Session = Depends(get_session),
):
    xml_bytes = await request.body()
    raw_status = parse_pain002(xml_bytes.decode("utf-8"))  # PaymentStatus enum or raw
    # Map ISO status to internal literal
    iso_map = {
        "ACSC": "SETTLED",
        "ACTC": "ACCEPTED",
        "RJCT": "REJECTED",
    }
    internal = iso_map.get(raw_status.value if hasattr(raw_status, "value") else str(raw_status), "UNKNOWN")
    order_id = request.headers.get("X-Order-ID")
    if order_id:
        row: SweepOrder | None = session.exec(select(SweepOrder).where(SweepOrder.order_id == order_id)).first()
        if row:
            row.status = internal
            session.add(row)
            session.commit()
    return PaymentStatusResponse(status=internal)


@app.get("/healthz")
async def healthz():
    return {"ok": True}


@app.post("/sweep-order")
async def create_sweep_order(
    payload: SweepOrderRequest, session: Session = Depends(get_session)
):
    # xml = create_pain_001(
    #     payload.order_id, payload.amount, payload.currency, payload.debtor, payload.creditor
    # )
    xml = "<pain.001></pain.001>"  # Stubbed XML
    start = time.perf_counter()
    bank_api_url = os.getenv("BANK_API_URL", "http://localhost:8000")
    async with httpx.AsyncClient() as client:
        await client.post(
            bank_api_url, data=xml, headers={"Content-Type": "application/xml"}
        )
    sweep_latency_seconds.observe(time.perf_counter() - start)

    order = SweepOrder(
        order_id=payload.order_id,
        amount=payload.amount,
        currency=payload.currency,
        debtor=payload.debtor,
        creditor=payload.creditor,
        status="SENT",
    )
    session.add(order)
    session.commit()
    session.refresh(order)
    return {"id": order.id}


@app.post("/payment-status")
async def payment_status(
    request: Request, session: Session = Depends(get_session)
) -> PaymentStatusResponse:
    xml = await request.body()
    # status = parse_pain_002(xml.decode())
    status = "UNKNOWN"  # Stubbed status
    order_id = request.headers.get("X-Order-ID")
    result = (
        session.exec(select(SweepOrder).where(SweepOrder.order_id == order_id)).first()
        if order_id
        else None
    )
    if result:
        result.status = status
        session.add(result)
        session.commit()
    return PaymentStatusResponse(status=status)
