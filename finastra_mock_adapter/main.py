import asyncio
import random
from fastapi import FastAPI, Response

try:
    from prometheus_fastapi_instrumentator import Instrumentator
    HAVE_INSTR = True
except Exception:  # pragma: no cover
    HAVE_INSTR = False

from prometheus_client import Counter

mock_adapter_requests_total = Counter(
    "mock_adapter_requests_total", "Total mock adapter requests"
)

app = FastAPI()

@app.middleware("http")
async def inject_jitter_and_errors(request, call_next):
    mock_adapter_requests_total.inc()
    await asyncio.sleep(random.uniform(0.05, 0.5))
    if random.random() < 0.05:
        return Response("Mock 500 error", status_code=500)
    return await call_next(request)

@app.get("/ping")
async def ping():
    return {"ok": True}

if HAVE_INSTR:
    Instrumentator().instrument(app).expose(app)
