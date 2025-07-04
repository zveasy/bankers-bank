# Mock API Endpoints for Dev/Test

This document lists all mock endpoints, their purposes, expected inputs, and sample responses. Use these endpoints for development and integration while the Finastra sandbox is unavailable.

---

## How to test with fastapi

### 1. install fastapi

 pip install fastapi uvicorn

### 2. start the mock server

run this command in terminal: uvicorn mocks.mock_finastra_api:app --reload

### 3. Run these commands in another terminal

python -m integration-client.test_sdk
python -m integration-client.test_negative_cases

## Base URL

<http://127.0.0.1:8000>

---

## Tested Error Scenarios

The following negative scenarios are handled and tested in the mock API:

- Payment to blocked recipient (403)
- Payment with invalid amount (400)
- Account not found (404)
- Collateral registration with zero valuation (400)
- Collateral registration with missing owner (400)
- Collateral registration for duplicate address (409)

For each, the mock API returns the expected error response for integration testing.

## Endpoints

### 1. List Accounts

**GET** `/corporate/channels/accounts/me/v1/accounts?accountContext=VIEW-ACCOUNT`

**Sample Response:**

```json
{
  "items": [
    {
      "id": "456783434",
      "number": "DE89 3704 0044 0532 0130 00",
      "currency": "USD",
      "accountContext": "VIEW-ACCOUNT",
      "type": "CURRENT"
    }
  ],
  "_meta": {
    "limit": 5,
    "pageCount": 12,
    "itemCount": 63
  }
}
```

---

### 2. Account Balances

**GET** `/corporate/channels/accounts/me/v1/accounts/{accountId}/balances`

**Sample Response:**

```json
{
  "items": [
    { "type": "BOOKED", "amount": 10500.0, "currency": "USD" },
    { "type": "AVAILABLE", "amount": 10250.0, "currency": "USD" }
  ],
  "_meta": { "itemCount": 2 }
}
```

---

### 3. List Transactions

**GET** `/corporate/channels/accounts/me/v1/accounts/{accountId}/transactions`

**Sample Response:**

```json
{
  "items": [
    { "transactionId": "txn-12345", "amount": -250.0, "currency": "USD", "date": "2024-06-12", "description": "ATM Withdrawal", "type": "DEBIT" },
    { "transactionId": "txn-12346", "amount": 1000.0, "currency": "USD", "date": "2024-06-10", "description": "Payroll Deposit", "type": "CREDIT" }
  ],
  "_meta": { "limit": 10, "pageCount": 1, "itemCount": 2 }
}
```

---

### 4. Initiate Payment

**POST** `/corporate/channels/accounts/me/v1/payments`

**Sample Request Body:**

```json
{
  "debtorAccount": { "id": "456783434" },
  "creditorAccount": { "name": "Jane Smith", "number": "NL91 ABNA 0417 1643 00" },
  "amount": 200.0,
  "currency": "USD",
  "remittanceInformation": "Invoice #12345"
}
```

**Sample Success Response:**

```json
{
  "paymentId": "pay-98765",
  "status": "CONFIRMED",
  "details": {
    "debtorAccount": { "id": "456783434", "number": "DE89 3704 0044 0532 0130 00" },
    "creditorAccount": { "name": "Jane Smith", "number": "NL91 ABNA 0417 1643 00" },
    "amount": 200.0,
    "currency": "USD",
    "remittanceInformation": "Invoice #12345"
  }
}
```

### 5. Register Collateral
  
  **POST** `/collateral`

  **Sample Request Body:**

  ```json
  {
    "address": "101 Market St",
    "valuation": 850000,
    "owner": "O&L Client A",
    "title_status": "Clean"
  }
  ```

  **Sample Success Response:**

  ```json
  {
    "id":"a8bc9bd0-daff-4870-abd1-aabf5566eded",
    "status": "REGISTERED"
  }
  ```
  
  **Error/Edge Case Responses:**

  **409 Conflict:**

  ```json
  {
    "detail": "Collateral at this address is already registered"
  }
  ```

  **400 Bad Request (zero valuation):**

  ```json
  {
    "detail": "Valuation must be a positive number"
  }
  ```

  **400 Bad Request (missing owner):**

  ```json
  {
    "detail": "Missing required field: owner"
  }
  ```

### 6. List Collateral

  **GET** `/collateral`

  **Sample Response:**

  ```json
  {
  "items": [
    {
      "address": "101 Market St",
      "valuation": 850000,
      "owner": "O&L Client A",
      "title_status": "Clean"
    }
  ]
  }
  ```

### 7. Calculate LTV (SDK helper)

While the mock API does not expose a dedicated endpoint for loan‑to‑value (LTV),
the Python SDK includes a helper that retrieves account balances and registered
collateral to compute the ratio.

```python
from bankersbank.client import BankersBankClient

client = BankersBankClient(base_url="http://127.0.0.1:8000", token="token")
ltv = client.calculate_ltv("456783434")
print(ltv)
```

The helper returns a dictionary containing the account ID, loan balance,
aggregate collateral valuation and the computed `ltv` value (e.g. `0.7`).

## Mocked Error Responses

### a. 403 Forbidden – Payment to Blocked Recipient

**POST** `/corporate/channels/accounts/me/v1/payments`

**Sample Error Response:**

```json
{
  "error": "RecipientBlocked",
  "message": "The payment recipient is blocked."
}
```

---

### b. 400 Bad Request – Invalid Payment Amount

**POST** `/corporate/channels/accounts/me/v1/payments`

**Sample Error Response:**

```json
{
  "error": "InvalidAmount",
  "message": "Payment amount must be greater than zero."
}
```

---

### c. 404 Not Found – Account Not Found

**GET** `/corporate/channels/accounts/me/v1/accounts/{invalidAccountId}`

**Sample Error Response:**

```json
{
  "error": "AccountNotFound",
  "message": "No account found with the provided ID."
}
```

---

## Usage Notes

- The mock server does not require authentication headers, but you can include them for testing.
- Make sure to adjust `localhost:8000` if running on a different port or machine.
- Add new endpoints and error cases here as you expand mocks.

---
Last updated: 2025-06-27
