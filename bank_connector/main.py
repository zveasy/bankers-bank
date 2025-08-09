import os
import time

import httpx
from fastapi import Depends, FastAPI, Request, Response
from prometheus_client import make_asgi_app
from sqlmodel import Session, select

from treasury_observability.metrics import sweep_latency_seconds

from .db import SweepOrder, get_session, init_db
from .models import PaymentStatusResponse, SweepOrderRequest

# from .iso20022 import create_pain_001, parse_pain_002

app = FastAPI()

init_db()

# Expose Prometheus metrics
app.mount("/metrics", make_asgi_app())


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
