# Finastra Integration Runbook

_Last updated: 2025-09-21_

---

## 1. Authentication (OAuth2 Client Credentials)

• Tokens come from `POST ${FINASTRA_BASE_URL}/login/v1/${FINASTRA_TENANT}/oidc/token`.
• `ClientCredentialsTokenProvider` caches & auto-refreshes (~60 s before expiry).
• Common errors
  | Status | Meaning | Fix |
  | ------ | ------- | --- |
  | 400    | bad request / wrong scope | ensure `scope` matches product (e.g. `accounts`) |
  | 401/403 | invalid creds / token expired | verify `FINASTRA_CLIENT_ID/SECRET`, clock skew |

Quick curl for diagnostics:
```bash
curl -s -XPOST -d "grant_type=client_credentials&client_id=$FINASTRA_CLIENT_ID&client_secret=$FINASTRA_CLIENT_SECRET" \
     "$FINASTRA_BASE_URL/login/v1/$FINASTRA_TENANT/oidc/token" | jq .
```

Env vars:
```
FINASTRA_CLIENT_ID  FINASTRA_CLIENT_SECRET
FINASTRA_BASE_URL   FINASTRA_TENANT
FINASTRA_PRODUCT_ACCOUNTS  FINASTRA_PRODUCT_COLLATERAL
FINASTRA_PRODUCT_PAYMENTS  FINASTRA_PRODUCT_LOANS
USE_MOCK_BALANCES
```

---

## 2. Rate Limits & 429 Handling

`FinastraAPIClient` retries idempotent GETs on 429/500-504 with exponential back-off.
If 429 persists:
• reduce concurrency  • verify tenant quotas  • contact Finastra support.

Metric `_non_2xx_total{status_bucket="4xx|5xx"}` will spike.

---

## 3. IP Allow-list & TLS / mTLS

• Sandbox/Prod may restrict to whitelisted IPs → ensure runner egress IPs registered.
• Some products use mutual-TLS — set `REQUESTS_CA_BUNDLE` to supplied PEM.

---

## 4. Local Development & Mocks

`USE_MOCK_BALANCES=true` forces the client to hit the local mock FastAPI server
(http://127.0.0.1:8000).  CI uses this mode so tests run without external access.

---

## 5. Payments & Loans Endpoints (sync client)

| Method | HTTP | Notes |
| ------ | ---- | ----- |
| `payments_initiate` | POST /payments | adds `X-Request-ID` idempotency header |
| `payments_status`   | GET  /payments/{id} |  |
| `loans_get`         | GET  /loans/{id} |  |
| `loans_list`        | GET  /loans | paging via `startingIndex/pageSize` |

---

## 6. Prometheus Metrics

| Metric | Type |
| ------ | ---- |
| `payments_initiate_total` | Counter `{result="success|error"}` |
| `payments_status_total`   | Counter `{result=…}` |
| `loans_read_total`        | Counter `{endpoint="get|list", result=…}` |
| `finastra_pay_loans_latency_seconds` | Histogram |
| `finastra_non_2xx_total`  | Counter `{status_bucket="4xx|5xx"}` |

If `prometheus_client` is absent, the library falls back to no-op stubs so unit tests still run.

---

## 7. Troubleshooting Checklist
1. Confirm env vars.
2. Run smoke test: `pytest -q tests/test_finastra_client.py::test_live_list_collaterals_smoke`
3. 429s? → throttle / back-off.
4. Cert or IP issues? → verify allow-list, `REQUESTS_CA_BUNDLE`.
