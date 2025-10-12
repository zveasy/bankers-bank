# Finastra Integration (B2B Collaterals / B2C Stubs)

## Overview
- **B2B (Collaterals)**: Live integration with retries, circuit breaker, Prometheus metrics, and structured logs. CI includes live smoke(s) when secrets are set.
- **B2C (Accounts/Balances)**: Stubbed and feature-flagged behind `FEATURE_FINASTRA_B2C=1` (no live calls until upstream stabilizes).

## Environment Variables

| Name                                  | Description                                           | Default / Example                         |
|---------------------------------------|-------------------------------------------------------|-------------------------------------------|
| `FINASTRA_B2B_CLIENT_ID`              | OAuth client id (B2B)                                 | —                                         |
| `FINASTRA_B2B_CLIENT_SECRET`          | OAuth client secret (B2B)                             | —                                         |
| `FINASTRA_B2B_BASE_URL_COLLATERALS`   | API base (Collaterals)                                | `https://api.fusionfabric.cloud`          |
| `FINASTRA_TENANT`                     | Tenant                                                | `sandbox`                                  |
| `FINASTRA_SCOPE`                      | OAuth scopes                                          | `openid`                                   |
| `FINASTRA_AUTH_URL`                   | Preferred auth host (scheme+netloc) for token URL     | `https://api.fusionfabric.cloud`          |
| `FINASTRA_TOKEN_URL`                  | Full token URL override (if set, used directly)       | `https://api.fusionfabric.cloud/login/v1/sandbox/oidc/token` |
| `FEATURE_FINASTRA_COLLATERALS`        | Feature flag for B2B routes                           | `1`                                        |
| `FEATURE_FINASTRA_B2C`                | Feature flag for B2C stub routes                      | `0`                                        |
| `FEATURE_FINASTRA_BREAKER`            | Enable circuit breaker                                | `1`/`0`                                    |
| `FINASTRA_BREAKER_FAIL_THRESHOLD`     | Consecutive failures to open breaker                  | `5` (CI tests use `2`)                     |
| `FINASTRA_BREAKER_COOLDOWN_SEC`       | Cooldown before half-open                             | `30`                                       |
| `FINASTRA_RETRY_MIN_SLEEP_MS`         | Minimum pacing sleep added after backoff (ms)         | e.g., `50`                                 |
| `TEST_COLLATERAL_ID_PRIMARY`          | Known collateral id for by-id live smoke              | —                                         |
| `FINASTRA_REQUIRE_200`                | If `1`, by-id live smoke requires 200 (strict mode)   | `0`                                        |

## Circuit Breaker
States: `closed → open → half → (closed|open)`
- **Open** after N consecutive terminal failures (`FINASTRA_BREAKER_FAIL_THRESHOLD`).
- While **open**, calls fast-fail with `RuntimeError("circuit_open")` until cooldown elapses.
- After cooldown, **half-open** allows one trial request:
  - Success → reset fail count, transition to `closed`.
  - Failure → transition back to `open` and start a new cooldown.

Configuration is read on `FinastraAPIClient` construction, so set env vars before instantiation.

## Metrics (Prometheus)
The API process exposes Prometheus metrics at `/metrics` via `prometheus_client`.

Core, product-agnostic series (exported from `bankersbank/finastra.py`):
- `finastra_api_calls_total{endpoint,status}`
- `finastra_api_latency_seconds{endpoint}` (histogram)

Circuit breaker gauge:
- `finastra_breaker_state{client}` where `client="collateral"` and values are `0=closed`, `1=half`, `2=open`.

Example checks:
```bash
# verify metrics show up
curl -s http://localhost:8050/metrics | grep finastra_api_calls_total || true
curl -s http://localhost:8050/metrics | grep finastra_api_latency_seconds || true
```

## B2B Routes (Asset Aggregator)
- `GET /finastra/b2b/collaterals` — list collaterals (query: `top`, `startingIndex`).
- `GET /finastra/b2b/collaterals/{collateral_id}` — get by id.


## B2C Stubs
- `GET /finastra/b2c/accounts` — stubbed list (feature-flagged).
- `GET /finastra/b2c/balances` — stubbed balances (feature-flagged).

Enable with `FEATURE_FINASTRA_B2C=1`. No live calls are made until the upstream stabilizes.

## Smokes
- Live list smoke (already present):
  ```bash
  pytest -q -m finastra_live tests/test_finastra_client.py -k test_live_list_collaterals_smoke
  ```
- Live by-id smoke (added):
  ```bash
  pytest -q -m finastra_live tests/test_finastra_client_live_by_id.py -k test_live_get_collateral_smoke
  ```
  By default, accepts `200` or `404`. Enable strict mode by setting `FINASTRA_REQUIRE_200=1` to require `200`.
- Runtime metrics smoke:
  ```bash
  python scripts/smoke_finastra_collateral.py --url http://127.0.0.1:8050
  ```

## Operational Monitoring Setup

- **Import Grafana dashboards** (Grafana → Dashboards → Import):
  - `infra/grafana/finastra_overview.json`
  - `infra/grafana/risk_exposure.json`
  - `infra/grafana/treasury_liquidity.json`

- **Load Prometheus rules**:
  - Alerts: `prometheus/rules/finastra_alerts.yml`
  - Recording: `prometheus/rules/finastra_recording.yml`
  - In Prometheus `prometheus.yml`, include these files under `rule_files:` and reload Prometheus.

- **CI metrics smoke artifacts (7 days retention)**:
  - GitHub → Actions → `metrics-smoke` workflow → latest run → Artifacts section.
  - Per-service artifact names: `metrics-bank_connector`, `metrics-treasury_observability`, `metrics-risk_guardrails`.

- **Quick curl check**:
  ```bash
  curl -s "$BANK_CONNECTOR_URL/metrics" | grep finastra_request_latency_seconds || true
  ```

## CI
Workflow: `.github/workflows/ci.yml`
- Precheck job surfaces `TEST_COLLATERAL_ID_PRIMARY` presence.
- Live smoke job runs list and by-id tests when secrets exist.
- `FINASTRA_SCOPE` is passed through from secrets.
 - Optional gate: set repo variable `RUN_FINASTRA_LIVE` to `0` to skip live smokes; any other value (or unset) runs them when secrets are present.

### Grafana Panels (PromQL)

- Error rate (5m window):
  ```promql
  sum(rate(finastra_api_calls_total{status!~"2.."}[5m]))
  /
  ignoring(status) sum(rate(finastra_api_calls_total[5m]))
  ```

- Error rate by endpoint:
  ```promql
  sum by (endpoint) (rate(finastra_api_calls_total{status!~"2.."}[5m]))
  ```

- P95 latency (5m window):
  ```promql
  histogram_quantile(
    0.95,
    sum by (le, endpoint) (rate(finastra_api_latency_seconds_bucket[5m]))
  )
  ```

- Calls per second by endpoint and status:
  ```promql
  sum by (endpoint, status) (rate(finastra_api_calls_total[5m]))
  ```

- Breaker open alert (open in last 5m):
  ```promql
  max_over_time(finastra_breaker_state{client="collateral"}[5m]) == 2
  ```
