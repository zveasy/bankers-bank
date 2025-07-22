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
./scripts/bootstrap_dev.sh          # spins up Postgres, Kafka, services

# run Go unit tests
make test

# regenerate SDKs when OpenAPI changes
make gen-sdk

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

## Mock API Endpoints

> For local dev/testing without live Finastra sandbox, see:

- docs/mock_api_endpoints.md

Detailed instructions for obtaining OAuth tokens and calling the Finastra
sandbox APIs are available in `docs/finastra_api.md`.

Last updated: 2025-06-27
