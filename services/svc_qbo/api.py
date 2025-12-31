# services/svc_qbo/api.py
# Minimal FastAPI microservice exposing QuickBooks (QBO) helper endpoints.
# Requires: fastapi, uvicorn, prometheus-client
#   poetry add fastapi uvicorn prometheus-client

import os
import time
import json
import base64
import requests
from fastapi import FastAPI, HTTPException
from prometheus_client import Counter, Gauge, Histogram, generate_latest, CONTENT_TYPE_LATEST
from dotenv import load_dotenv

# Load .env.local into environment
load_dotenv(dotenv_path=".env.local")

# ---- Env vars ----
CLIENT_ID = os.getenv("QBO_CLIENT_ID")
CLIENT_SEC = os.getenv("QBO_CLIENT_SECRET")
REALM_ID = os.getenv("QBO_REALM")
REDIRECT_URI = os.getenv("QBO_REDIRECT_URI", "http://localhost:8000/callback")
TOKEN_PATH = "secrets/qbo_token.json"

# ---- Metrics ----
REQ_COUNT = Counter("qbo_requests_total", "Total QBO API requests", ["endpoint", "status"])
REQ_ERRORS = Counter("qbo_errors_total", "Total QBO API errors", ["endpoint"])
QBO_LATENCY = Histogram(
    "qbo_api_latency_seconds",
    "Latency for QBO API endpoints",
    ["endpoint"],
    buckets=(0.05, 0.1, 0.2, 0.5, 1, 2, 5, 10)
)
QBO_API_ERRORS = Counter(
    "qbo_api_error_total",
    "Total QBO API errors (final)",
    ["endpoint"]
)
LAST_REFRESH_TS = Gauge("qbo_last_refresh_timestamp", "Timestamp of last token refresh")

# ---- FastAPI app ----
app = FastAPI(title="svc-qbo", version="1.0.0")

# ---- Helper: token management ----
def load_tokens():
    if not os.path.exists(TOKEN_PATH):
        raise FileNotFoundError(f"Token file missing: {TOKEN_PATH}")
    with open(TOKEN_PATH, "r") as f:
        return json.load(f)

def save_tokens(data):
    os.makedirs(os.path.dirname(TOKEN_PATH), exist_ok=True)
    with open(TOKEN_PATH, "w") as f:
        json.dump(data, f, indent=2)

def basic_auth_header():
    creds = f"{CLIENT_ID}:{CLIENT_SEC}".encode()
    return base64.b64encode(creds).decode()

def refresh_access_token():
    tokens = load_tokens()
    refresh_token = tokens.get("refresh_token")
    resp = requests.post(
        "https://oauth.platform.intuit.com/oauth2/v1/tokens/bearer",
        headers={
            "Authorization": f"Basic {basic_auth_header()}",
            "Accept": "application/json",
            "Content-Type": "application/x-www-form-urlencoded"
        },
        data={
            "grant_type": "refresh_token",
            "refresh_token": refresh_token
        },
        timeout=15
    )
    if resp.status_code != 200:
        REQ_ERRORS.labels("refresh").inc()
        raise HTTPException(status_code=resp.status_code, detail=resp.text)
    data = resp.json()
    save_tokens({**tokens, **data})
    LAST_REFRESH_TS.set(int(time.time()))
    return data["access_token"]

def qbo_request(endpoint, query=None):
    start = time.monotonic()
    tokens = load_tokens()
    access_token = tokens.get("access_token")
    url = f"https://sandbox-quickbooks.api.intuit.com/v3/company/{REALM_ID}/{endpoint}"
    headers = {"Authorization": f"Bearer {access_token}", "Accept": "application/json"}
    if query:
        url = f"{url}?query={query}"
    try:
        r = requests.get(url, headers=headers, timeout=20)
        if r.status_code == 401:
            access_token = refresh_access_token()
            headers["Authorization"] = f"Bearer {access_token}"
            r = requests.get(url, headers=headers, timeout=20)
        REQ_COUNT.labels(endpoint=endpoint, status=r.status_code).inc()
        r.raise_for_status()
        return r.json()
    except Exception:
        QBO_API_ERRORS.labels(endpoint=endpoint).inc()
        REQ_ERRORS.labels(endpoint).inc()
        raise
    finally:
        QBO_LATENCY.labels(endpoint=endpoint).observe(max(0, time.monotonic() - start))

# ---- Routes ----
@app.get("/healthz")
def healthz():
    """Fast liveness check."""
    return {"status": "up", "service": "svc-qbo"}

@app.get("/readyz")
def readyz():
    """Readiness check: validate refresh works."""
    try:
        _ = refresh_access_token()
        return {"status": "ready", "ts": int(time.time())}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"refresh failed: {e}")

@app.get("/qbo/companyinfo")
def get_company_info():
    return qbo_request("companyinfo/1")

@app.get("/qbo/query")
def query_qbo(q: str):
    return qbo_request("query", query=q)

@app.get("/metrics")
def metrics():
    return generate_latest(), 200, {"Content-Type": CONTENT_TYPE_LATEST}
