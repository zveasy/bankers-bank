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

### Quick-start

```bash
#  clone & bootstrap
git clone git@github.com:OandL/bankers-bank.git && cd bankers-bank
./scripts/bootstrap_dev.sh          # spins up Postgres, Kafka, services

# run Go unit tests
make test

# regenerate SDKs when OpenAPI changes
make gen-sdk
