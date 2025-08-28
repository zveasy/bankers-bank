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
1. Copy `.env.example` to `.env` and fill in `FINA_CLIENT_ID` / `FINA_CLIENT_SECRET` from the Finastra portal.
2. Adjust scope or flow flags if you enable new products.
3. The optional `FINA_TOKEN_SKEW_SECONDS` (default `30`) refreshes tokens *N* seconds before expiry to avoid edge-case 401s.
4. **Never commit your real `.env`.** CI picks secrets from GitHub Actions `Secrets`/`Variables` as documented.

Minimal local example:
```bash
cp .env.example .env
export FINA_CLIENT_ID=xxxx FINA_CLIENT_SECRET=yyyy
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

Last updated: 2025-06-27
