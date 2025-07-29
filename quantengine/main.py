import os
from fastapi import FastAPI, Depends, HTTPException
import redis
from prometheus_client import make_asgi_app
from sqlmodel import Session
from treasury_observability.metrics import treas_ltv_ratio as ltv_gauge

from .db import init_db, get_session, get_cash

app = FastAPI()
init_db()

REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")
redis_client = redis.Redis.from_url(REDIS_URL)

app.mount("/metrics", make_asgi_app())


@app.get("/investable-cash")
def investable_cash(bank_id: str, session: Session = Depends(get_session)):
    val = redis_client.get(f"cash_available:{bank_id}")
    if val is not None:
        cash = float(val)
    else:
        db_cash = get_cash(session, bank_id)
        if db_cash is None:
            raise HTTPException(status_code=404, detail="bank not found")
        cash = db_cash
    return {"cash": cash}
