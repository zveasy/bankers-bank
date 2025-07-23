import os
import time
from fastapi import FastAPI, Response, Depends, Request
import httpx
from sqlmodel import Session, select

from .db import SweepOrder, init_db, get_session
from .models import SweepOrderRequest, PaymentStatusResponse
from treasury_observability.metrics import sweep_latency_seconds
# from .iso20022 import create_pain_001, parse_pain_002

app = FastAPI()

init_db()

BANK_API_URL = os.getenv("BANK_API_URL", "http://localhost:9999")


@app.post("/sweep-order")
async def create_sweep_order(payload: SweepOrderRequest, session: Session = Depends(get_session)):
    # xml = create_pain_001(
    #     payload.order_id, payload.amount, payload.currency, payload.debtor, payload.creditor
    # )
    xml = "<pain.001></pain.001>"  # Stubbed XML
    start = time.perf_counter()
    async with httpx.AsyncClient() as client:
        await client.post(BANK_API_URL, data=xml, headers={"Content-Type": "application/xml"})
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
async def payment_status(request: Request, session: Session = Depends(get_session)) -> PaymentStatusResponse:
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
