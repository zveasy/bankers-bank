# Banker’s Bank Platform

> Internal API + modular SDK powering O&L’s “bank-as-a-banker” model.

### Vision
Build a regulated, capital-efficient core so regional banks can:
1.  park excess deposits (sweeps) and earn on-platform yield,
2.  access secured credit lines for energy-infrastructure deals,
3.  settle payments & collateral almost real-time (FedNow rails).

### Repo layout
| Path            | Purpose                            |
|-----------------|------------------------------------|
| `/api`          | REST & gRPC contracts (OpenAPI v3) |
| `/services`     | Go micro-services (hexagonal)      |
| `/sdk`          | Auto-generated typed clients       |
| `/infra`        | Terraform + Kustomize IaC          |
| `/docs`         | Architecture, ADRs, runbooks       |
| `/asset_aggregator` | Python service for asset snapshots |

### Quick-start

```bash
#  clone & bootstrap
git clone git@github.com:OandL/bankers-bank.git && cd bankers-bank
make init-db                        # initialise local SQLite files
./scripts/bootstrap_dev.sh          # spins up Postgres, Kafka, services

# run Go unit tests
make test

# regenerate SDKs when OpenAPI changes
make gen-sdk

```

### Configuration

#### Finastra OAuth setup
1. Store `FINA_CLIENT_ID` / `FINA_CLIENT_SECRET` in a JSON file referenced by
   the `SECRETS_PATH` environment variable. This file acts as a lightweight
   secrets manager for local development.
2. Adjust scope or flow flags if you enable new products.
3. The optional `FINA_TOKEN_SKEW_SECONDS` (default `30`) refreshes tokens *N*
   seconds before expiry to avoid edge-case 401s.
4. **Never commit your real secret files.** CI picks secrets from GitHub
   Actions `Secrets`/`Variables` as documented.

Minimal local example:
```bash
cp .env.example .env
echo '{"FINA_CLIENT_ID":"xxxx","FINA_CLIENT_SECRET":"yyyy"}' > .secrets.json
export SECRETS_PATH=$PWD/.secrets.json
python -m asset_aggregator.main  # provider auto-selects grant type per slice
```


Copy `.env.example` to `.env` and set your database credentials. Docker Compose
and the Helm chart reference these variables at runtime.

```bash
cp .env.example .env
# edit as needed, then for Helm deployments:
export $(grep -v '^#' .env | xargs)
envsubst < kubernetes/helm/values.yaml | helm install bankers-bank kubernetes/helm -f -
```

### Docker quick-start

```bash
# build and start all containers in the background
docker compose up --build -d

# Open service docs (Windows `start` opens default browser)
start https://localhost:8003/docs  # Bank Connector
start https://localhost:9000/docs  # Asset Aggregator

# stop and remove containers, networks, volumes
docker compose down -v
```

### Gateway API (Dockerfile build)

The Gateway API now builds via a dedicated Dockerfile (no runtime pip installs).

```bash
# build only gateway_api image
docker compose build gateway_api

# start gateway_api and svc_qbo
docker compose up -d svc_qbo gateway_api

# healthcheck turns green quickly (short start_period)
curl -s http://127.0.0.1:8057/healthz

# proxy examples
curl -s http://127.0.0.1:8057/qbo/companyinfo | jq .
curl -s "http://127.0.0.1:8057/qbo/query?q=$(python - <<'PY'\nimport urllib.parse\nprint(urllib.parse.quote('select * from Account startposition 1 maxresults 5'))\nPY\n)" | jq .
```

### QuickBooks OAuth token setup (svc_qbo)

`services/svc_qbo` expects a token file at `secrets/qbo_token.json` and the following envs in `.env.local`:

```bash
QBO_CLIENT_ID=...           # Intuit app client id
QBO_CLIENT_SECRET=...       # Intuit app client secret
QBO_REALM=...               # Company realm id
QBO_REDIRECT_URI=http://localhost:8000/callback
```

Token file minimal shape (sandbox example):

```json
{
  "access_token": "...",
  "refresh_token": "..."
}
```

The service will auto-refresh tokens on 401 and update `secrets/qbo_token.json`.

### CI healthchecks and daily metrics smoke

- GitHub Actions workflow `metrics-smoke.yml` runs daily and can be triggered manually.
- Set repository Variables with publicly reachable URLs for these services:
  - `BANK_CONNECTOR_URL`, `TREASURY_OBS_URL`, `RISK_GUARDRAILS_URL`, `SVC_QBO_URL`, `GATEWAY_API_URL`
- The workflow fetches `/metrics` for each configured service and, for QBO/gateway, hits:
  - `GET /healthz`
  - `GET /qbo/companyinfo`
  - `GET /qbo/query?q=select * from Account ...`
- Artifacts (7-day retention) include raw metrics and JSON responses; a summary is appended to the run page.

### Grafana dashboards

Grafana runs with authentication enabled and is only bound to `localhost` to
avoid exposing dashboards beyond internal networks.

1.  Set credentials in `.env`:

    ```bash
    GF_ADMIN_USER=admin
    GF_ADMIN_PASSWORD=changeme
    ```

2.  Start the stack with `docker compose up`.
3.  Browse to [http://localhost:3000](http://localhost:3000) and log in with the
    credentials above.
4.  Do not publish the Grafana port publicly without additional network
    protections (VPN, firewall, etc.).

### Health & smoke

- Health endpoints:
  - Bank-Connector: `GET https://localhost:8003/healthz`
  - Asset-Aggregator: `GET https://localhost:9000/healthz`

- Smoke test:
  ```bash
  docker compose up -d
  python scripts/smoke_e2e.py
  docker compose down -v
  ```

## Python SDK (bankersbank)

> Use the Python SDK for API integration and testing.

### Install the SDK locally

```bash

pip install sdk/python/dist/bankersbank-0.1.0-py3-none-any.whl

```

### Example Usage

```python

from bankersbank import BankersBankClient

client = BankersBankClient(...)
accounts = client.list_accounts()
print(accounts)

```

### Enable SDK logging

The SDK emits debug-level logs with HTTP status codes and responses. To
surface these logs in your application, configure Python's logging module:

```python
import logging

logging.basicConfig(level=logging.DEBUG)
```

## Mock API Endpoints

> For local dev/testing without live Finastra sandbox, see:

- docs/mock_api_endpoints.md

Detailed instructions for obtaining OAuth tokens and calling the Finastra
sandbox APIs are available in `docs/finastra_api.md`.

## License

License **pending legal review** – no license is currently granted. See [`LICENSE.draft`](LICENSE.draft) for the proposed MIT terms.

Last updated: 2025-06-27

