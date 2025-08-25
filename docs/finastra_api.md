# Finastra API Integration

This guide describes how to authenticate with Finastra's sandbox and call the
Account Information and Collateral APIs used for LTV calculations.

## Obtain an OAuth Token

Use the provided helper script:

```bash
export FFDC_CLIENT_ID=<your-client-id>
export FFDC_CLIENT_SECRET=<your-secret>
python scripts/fetch_token.py
```

Or call the function directly:

```python
from bankersbank.finastra import fetch_token

token = fetch_token("<client_id>", "<client_secret>")
```

## Fetch Accounts with Details

```python
from bankersbank.finastra import FinastraAPIClient

client = FinastraAPIClient(token, base_url="https://127.0.0.1:8000")
accounts = client.accounts_with_details("c123")
```

Sample response (see `mocks/fixtures/accounts_extended.json`):

```json
{
  "items": [
    {
      "accountId": "456783434",
      "accountType": "CURRENT",
      "balances": [
        {"type": "BOOKED", "amount": 10500.0, "currency": "USD"},
        {"type": "AVAILABLE", "amount": 10250.0, "currency": "USD"}
      ],
      "owner": {"consumerId": "c123", "name": "O&L Client A"}
    }
  ]
}
```

## Fetch Collateral for an Account

```python
collateral = client.collaterals_for_account("456783434")
```

Sample response (`mocks/fixtures/collaterals_for_account.json`):

```json
{
  "items": [
    {"collateralId": "col-001", "accountId": "456783434", "description": "HQ Building", "valuation": 850000.0},
    {"collateralId": "col-002", "accountId": "456783434", "description": "Vehicle Fleet", "valuation": 200000.0}
  ]
}
```

## Calculate LTV

```python
result = client.calculate_ltv("c123")
print(result)
```

---
Last updated: 2025-07-04
