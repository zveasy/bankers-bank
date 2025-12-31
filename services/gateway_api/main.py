# services/gateway_api/main.py
# Gateway microservice: exposes unified endpoints, proxies to svc-qbo and others.

from fastapi import FastAPI, HTTPException
import httpx, os, time
from prometheus_client import Histogram, Counter, generate_latest, CONTENT_TYPE_LATEST

app = FastAPI(title="gateway_api", version="1.0.0")

# Environment variable (you can later move this into your .env.local)
QBO_URL = os.getenv("SVC_QBO_URL", "http://127.0.0.1:8055")

# Metrics
QBO_LATENCY = Histogram(
    "qbo_api_latency_seconds",
    "Latency of QBO proxy calls",
    ["route"],
    buckets=(0.05, 0.1, 0.2, 0.5, 1, 2, 5, 10)
)
QBO_ERRORS = Counter(
    "qbo_api_error_total",
    "Total QBO proxy errors",
    ["route"]
)

@app.get("/healthz")
async def healthz():
    """Simple health check."""
    return {"status": "ok", "service": "gateway_api"}

@app.get("/qbo/companyinfo")
async def qbo_companyinfo():
    """Proxy to svc-qbo companyinfo endpoint."""
    start = time.monotonic()
    try:
        async with httpx.AsyncClient(timeout=20) as client:
            r = await client.get(f"{QBO_URL}/qbo/companyinfo")
        r.raise_for_status()
        return r.json()
    except httpx.RequestError as e:
        QBO_ERRORS.labels(route="companyinfo").inc()
        raise HTTPException(status_code=502, detail=f"QBO proxy failed: {e}")
    except httpx.HTTPStatusError as e:
        QBO_ERRORS.labels(route="companyinfo").inc()
        raise HTTPException(status_code=e.response.status_code, detail=e.response.text)
    finally:
        QBO_LATENCY.labels(route="companyinfo").observe(max(0, time.monotonic() - start))

@app.get("/qbo/query")
async def qbo_query(q: str):
    """Proxy to svc-qbo query endpoint."""
    start = time.monotonic()
    try:
        async with httpx.AsyncClient(timeout=30) as client:
            r = await client.get(f"{QBO_URL}/qbo/query", params={"q": q})
        r.raise_for_status()
        return r.json()
    except httpx.RequestError as e:
        QBO_ERRORS.labels(route="query").inc()
        raise HTTPException(status_code=502, detail=f"QBO proxy failed: {e}")
    except httpx.HTTPStatusError as e:
        QBO_ERRORS.labels(route="query").inc()
        raise HTTPException(status_code=e.response.status_code, detail=e.response.text)
    finally:
        QBO_LATENCY.labels(route="query").observe(max(0, time.monotonic() - start))

@app.get("/metrics")
async def metrics():
    return generate_latest(), 200, {"Content-Type": CONTENT_TYPE_LATEST}
