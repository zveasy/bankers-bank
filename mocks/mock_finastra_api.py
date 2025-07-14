from fastapi import FastAPI, Header, HTTPException, Query, Request, Body
from typing import Dict, Any
import uuid

app = FastAPI()

# In-memory store for collateral
collateral_store: Dict[str, Dict[str, Any]] = {}
collateral_registry = []
registered_addresses = set()

# --- Sample Data ---
SAMPLE_ACCOUNTS = [
    {
        "id": "456783434",
        "number": "DE89 3704 0044 0532 0130 00",
        "currency": "USD",
        "accountContext": "VIEW-ACCOUNT",
        "type": "CURRENT"
    },
    {
        "id": "123456789",
        "number": "GB82 WEST 1234 5698 7654 32",
        "currency": "GBP",
        "accountContext": "VIEW-ACCOUNT",
        "type": "SAVINGS"
    }
]

SAMPLE_BALANCES = {
    "456783434": [
        {"type": "BOOKED", "amount": 10500.0, "currency": "USD"},
        {"type": "AVAILABLE", "amount": 10250.0, "currency": "USD"}
    ],
    "123456789": [
        {"type": "BOOKED", "amount": 2200.0, "currency": "GBP"},
        {"type": "AVAILABLE", "amount": 2180.0, "currency": "GBP"}
    ]
}

SAMPLE_TRANSACTIONS = {
    "456783434": [
        {
            "transactionId": "txn-12345",
            "amount": -250.0,
            "currency": "USD",
            "date": "2024-06-12",
            "description": "ATM Withdrawal",
            "type": "DEBIT"
        },
        {
            "transactionId": "txn-12346",
            "amount": 1000.0,
            "currency": "USD",
            "date": "2024-06-10",
            "description": "Payroll Deposit",
            "type": "CREDIT"
        }
    ]
}

SAMPLE_BENEFICIARIES = [
    {
        "beneficiaryId": "ben-001",
        "name": "John Doe",
        "accountNumber": "NL91 ABNA 0417 1643 00",
        "bankName": "ABN AMRO"
    }
]

# --- Endpoints with Error Simulation ---

@app.get("/corporate/channels/accounts/me/v1/accounts")
def list_accounts(accountContext: str, authorization: str = Header(None)):
    # For dev: accept any non-empty auth header
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Unauthorized")
    # Example response
    return {
        "items": [
            {
                "id": "456783434",
                "number": "DE89 3704 0044 0532 0130 00",
                "currency": "USD",
                "accountContext": accountContext,
                "type": "CURRENT"
            }
        ],
        "_meta": {
            "limit": 5,
            "pageCount": 12,
            "itemCount": 63
        }
    }

@app.get("/corporate/channels/accounts/me/v1/accounts/{account_id}")
def get_account(account_id: str):
    # Simulate 404 for a fake/nonexistent account
    if account_id == "0000":
        raise HTTPException(status_code=404, detail="Account not found")
    for account in SAMPLE_ACCOUNTS:
        if account["id"] == account_id:
            return account
    raise HTTPException(status_code=404, detail="Account not found")

@app.get("/corporate/channels/accounts/me/v1/accounts/{account_id}/balances")
def get_account_balances(account_id: str, error: str = None):
    # Simulate error based on query
    if error == "500":
        raise HTTPException(status_code=500, detail="Simulated Internal Error")
    balances = SAMPLE_BALANCES.get(account_id)
    if not balances:
        raise HTTPException(status_code=404, detail="Account not found")
    return {
        "items": balances,
        "_meta": {"itemCount": len(balances)}
    }

@app.get("/corporate/channels/accounts/me/v1/accounts/{account_id}/transactions")
def get_account_transactions(account_id: str, limit: int = 10, offset: int = 0, error: str = None):
    # Simulate 403 forbidden for special param
    if error == "403":
        raise HTTPException(status_code=403, detail="Simulated Forbidden")
    txns = SAMPLE_TRANSACTIONS.get(account_id, [])
    return {
        "items": txns[offset:offset+limit],
        "_meta": {"limit": limit, "pageCount": 1, "itemCount": len(txns)}
    }

@app.get("/corporate/channels/accounts/me/v1/beneficiaries")
def get_beneficiaries(limit: int = 10, offset: int = 0, error: str = None):
    # Simulate 500 error for special param
    if error == "500":
        raise HTTPException(status_code=500, detail="Simulated Internal Error")
    return {
        "items": SAMPLE_BENEFICIARIES[offset:offset+limit],
        "_meta": {"limit": limit, "pageCount": 1, "itemCount": len(SAMPLE_BENEFICIARIES)}
    }

@app.post("/corporate/channels/accounts/me/v1/payments")
def make_payment(payload: dict = Body(...), authorization: str = Header(None)):
    # Amount check
    amount = payload.get("amount", 1)
    if amount <= 0:
        raise HTTPException(status_code=400, detail="Invalid amount")

    # Blocked recipient check
    creditor = payload.get("creditorAccount", {})
    blocked_names = {"Blocked Recipient", "Evil Corp"}  # add as many as you like
    if creditor.get("name") in blocked_names:
        raise HTTPException(status_code=403, detail="Beneficiary blocked")

    # Default: return mock success
    return {
        "paymentId": "pay-98765",
        "status": "CONFIRMED",
        "details": payload
    }

@app.get("/corporate/channels/accounts/me/v1/accounts/{account_id}/simulate-500")
def simulate_internal_error(account_id: str):
    raise HTTPException(status_code=500, detail="Internal server error")




@app.post("/collateral")
def post_collateral(payload: dict = Body(...)):
    # Validate required fields
    for field in ("address", "valuation", "owner", "title_status"):
        if field not in payload:
            raise HTTPException(status_code=400, detail=f"Missing required field: {field}")

    address = payload["address"]
    valuation = payload["valuation"]
    title_status = payload["title_status"]

    # Duplicate address
    if address in registered_addresses:
        raise HTTPException(status_code=409, detail="Collateral at this address is already registered")

    # Non-positive valuation
    if not isinstance(valuation, (int, float)) or valuation <= 0:
        raise HTTPException(status_code=400, detail="Valuation must be a positive number")

    # Disputed or blocked title
    if title_status.strip().lower() in {"disputed", "blocked"}:
        raise HTTPException(status_code=403, detail="Collateral title is disputed/blocked")

    # Register collateral
    registered_addresses.add(address)
    collateral_registry.append(payload)
    return {
        "id": "a8bc9bd0-daff-4870-abd1-aabf5566eded",
        "status": "REGISTERED"
    }

@app.get("/collateral")
def get_collateral():
    return {"items": collateral_registry}

@app.post("/ltv/calculate")
def calculate_ltv(payload: dict = Body(...)):
    """
    Calculate Loan-to-Value (LTV) ratio.
    Expects JSON: {"collateral_value": float, "loan_amount": float}
    Returns: {"ltv": float}
    """
    collateral_value = payload.get("collateral_value")
    loan_amount = payload.get("loan_amount")
    if collateral_value is None or loan_amount is None:
        raise HTTPException(status_code=400, detail="Missing collateral_value or loan_amount")
    if not isinstance(collateral_value, (int, float)) or not isinstance(loan_amount, (int, float)):
        raise HTTPException(status_code=400, detail="Values must be numeric")
    if collateral_value <= 0:
        raise HTTPException(status_code=400, detail="collateral_value must be positive")
    ltv = loan_amount / collateral_value
    return {"ltv": ltv}

@app.post("/collateral/reset")
def reset_collateral():
    """Reset the in-memory collateral registry and addresses for test isolation."""
    collateral_registry.clear()
    registered_addresses.clear()
    return {"status": "reset"}