# Asset Aggregator Service

This service periodically pulls balance and collateral data for partner banks and
stores a combined snapshot. A snapshot row is also published to Kafka so other
services can react to asset changes.

## Kafka Message

```
key   = <bank_id>
value = {
    "ts": ISO8601 timestamp,
    "eligibleCollateralUSD": float,
    "totalBalancesUSD": float,
    "undrawnCreditUSD": float
}
```

## REST API

- `GET /assets/summary?bank_id=123` – return the most recent snapshot for the
  bank.
- `GET /assets/history?bank_id=123&days=1` – return all snapshots captured in
  the last `days` days.
