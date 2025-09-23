from typing import Any, Dict, List, Optional, Set

from fastapi import Body, FastAPI, Header, HTTPException, Query, Request, Response

app = FastAPI()

# In-memory store for collateral
collateral_store: Dict[str, Dict[str, Any]] = {}
collateral_registry: List[Dict[str, Any]] = []
registered_addresses: Set[str] = set()

# --- Minimal endpoints for test_bank_connector.py ---
@app.post("/sweep-order")
async def sweep_order(request: Request) -> Response:
    # Accept any payload and return 200 OK
    return Response(content="<ok/>", media_type="application/xml", status_code=200)


@app.post("/payment-status")
async def payment_status(request: Request) -> Response:
    # Accept any payload and return 200 OK
    return Response(content="<ok/>", media_type="application/xml", status_code=200)


# --- Sample Data ---
SAMPLE_ACCOUNTS: List[Dict[str, Any]] = [
    {
        "id": "456783434",
        "number": "DE89 3704 0044 0532 0130 00",
        "currency": "USD",
        "accountContext": "VIEW-ACCOUNT",
        "type": "CURRENT",
    },
    {
        "id": "123456789",
        "number": "GB82 WEST 1234 5698 7654 32",
        "currency": "GBP",
        "accountContext": "VIEW-ACCOUNT",
        "type": "SAVINGS",
    },
]

SAMPLE_BALANCES: Dict[str, List[Dict[str, Any]]] = {
    "456783434": [
        {"type": "BOOKED", "amount": 10500.0, "currency": "USD"},
        {"type": "AVAILABLE", "amount": 10250.0, "currency": "USD"},
    ],
    "123456789": [
        {"type": "BOOKED", "amount": 2200.0, "currency": "GBP"},
        {"type": "AVAILABLE", "amount": 2180.0, "currency": "GBP"},
    ],
}

SAMPLE_TRANSACTIONS: Dict[str, List[Dict[str, Any]]] = {
    "456783434": [
        {
            "transactionId": "txn-12345",
            "amount": -250.0,
            "currency": "USD",
            "date": "2024-06-12",
            "description": "ATM Withdrawal",
            "type": "DEBIT",
        },
        {
            "transactionId": "txn-12346",
            "amount": 1000.0,
            "currency": "USD",
            "date": "2024-06-10",
            "description": "Payroll Deposit",
            "type": "CREDIT",
        },
    ]
}

SAMPLE_BENEFICIARIES: List[Dict[str, Any]] = [
    {
        "beneficiaryId": "ben-001",
        "name": "John Doe",
        "accountNumber": "NL91 ABNA 0417 1643 00",
        "bankName": "ABN AMRO",
    }
]

# --- Endpoints with Error Simulation ---

@app.get("/corporate/channels/accounts/me/v1/accounts")
def list_accounts(accountContext: str, authorization: str = Header(None)) -> Dict[str, Any]:
    # For dev: accept any non-empty auth header
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Unauthorized")
    return {
        "items": [
            {
                "id": "456783434",
                "number": "DE89 3704 0044 0532 0130 00",
                "currency": "USD",
                "accountContext": accountContext,
                "type": "CURRENT",
            }
        ],
        "_meta": {"limit": 5, "pageCount": 12, "itemCount": 63},
    }


@app.get("/corporate/channels/accounts/me/v1/accounts/{account_id}")
def get_account(account_id: str) -> Dict[str, Any]:
    if account_id == "0000":
        raise HTTPException(status_code=404, detail="Account not found")
    for account in SAMPLE_ACCOUNTS:
        if account["id"] == account_id:
            return account
    raise HTTPException(status_code=404, detail="Account not found")


@app.get("/corporate/channels/accounts/me/v1/accounts/{account_id}/balances")
def get_account_balances(
    account_id: str,
    error: Optional[str] = None,
    authorization: str = Header(None),
) -> Dict[str, Any]:
    if (
        not authorization
        or not authorization.startswith("Bearer ")
        or authorization not in ("Bearer dummy", "Bearer testtoken")
    ):
        raise HTTPException(status_code=401, detail="Unauthorized")
    if error == "500":
        raise HTTPException(status_code=500, detail="Simulated Internal Error")
    balances = SAMPLE_BALANCES.get(account_id)
    if not balances:
        raise HTTPException(status_code=404, detail="Account not found")
    return {"items": balances, "_meta": {"itemCount": len(balances)}}


@app.get("/corporate/channels/accounts/me/v1/accounts/{account_id}/transactions")
def get_account_transactions(
    account_id: str,
    limit: int = 10,
    offset: int = 0,
    error: Optional[str] = None,
) -> Dict[str, Any]:
    if error == "403":
        raise HTTPException(status_code=403, detail="Simulated Forbidden")
    txns = SAMPLE_TRANSACTIONS.get(account_id, [])
    return {
        "items": txns[offset : offset + limit],
        "_meta": {"limit": limit, "pageCount": 1, "itemCount": len(txns)},
    }


@app.get("/corporate/channels/accounts/me/v1/beneficiaries")
def get_beneficiaries(
    limit: int = 10, offset: int = 0, error: Optional[str] = None
) -> Dict[str, Any]:
    if error == "500":
        raise HTTPException(status_code=500, detail="Simulated Internal Error")
    return {
        "items": SAMPLE_BENEFICIARIES[offset : offset + limit],
        "_meta": {"limit": limit, "pageCount": 1, "itemCount": len(SAMPLE_BENEFICIARIES)},
    }


@app.post("/corporate/channels/accounts/me/v1/payments")
def make_payment(payload: Dict[str, Any] = Body(...), authorization: str = Header(None)) -> Dict[str, Any]:
    amount = payload.get("amount", 1)
    if amount <= 0:
        raise HTTPException(status_code=400, detail="Invalid amount")

    creditor = payload.get("creditorAccount", {})
    blocked_names = {"Blocked Recipient", "Evil Corp"}
    if creditor.get("name") in blocked_names:
        raise HTTPException(status_code=403, detail="Beneficiary blocked")

    return {"paymentId": "pay-98765", "status": "CONFIRMED", "details": payload}


@app.get("/corporate/channels/accounts/me/v1/accounts/{account_id}/simulate-500")
def simulate_internal_error(account_id: str) -> None:
    raise HTTPException(status_code=500, detail="Internal server error")


@app.post("/collateral")
def post_collateral(payload: Dict[str, Any] = Body(...)) -> Dict[str, Any]:
    for field in ("address", "valuation", "owner", "title_status"):
        if field not in payload:
            raise HTTPException(status_code=400, detail=f"Missing required field: {field}")

    address = payload["address"]
    valuation = payload["valuation"]
    title_status = payload["title_status"]

    if address in registered_addresses:
        raise HTTPException(status_code=409, detail="Collateral at this address is already registered")

    if not isinstance(valuation, (int, float)) or valuation <= 0:
        raise HTTPException(status_code=400, detail="Valuation must be a positive number")

    if str(title_status).strip().lower() in {"disputed", "blocked"}:
        raise HTTPException(status_code=403, detail="Collateral title is disputed/blocked")

    registered_addresses.add(address)
    collateral_registry.append(payload)
    return {"id": "a8bc9bd0-daff-4870-abd1-aabf5566eded", "status": "REGISTERED"}


@app.get("/collateral")
def get_collateral() -> Dict[str, Any]:
    return {"items": collateral_registry}


@app.get("/collaterals")
def list_collaterals(accountId: str = Query(...)) -> Dict[str, Any]:
    """Return collateral items for an account."""
    items = [
        c
        for c in collateral_registry
        if c.get("accountId", "") == accountId or c.get("address", "") == accountId
    ]
    return {"items": items}


@app.get("/consumers/{consumer_id}/accounts/extendedWithDetails")
def get_accounts_with_details(consumer_id: str) -> Dict[str, Any]:
    """Return accounts with balances for a consumer."""
    items = []
    for acc in SAMPLE_ACCOUNTS:
        items.append(
            {
                "accountId": acc["id"],
                "accountType": acc["type"],
                "balances": SAMPLE_BALANCES.get(acc["id"], []),
                "owner": {"consumerId": consumer_id, "name": "O&L Client A"},
            }
        )
    return {"items": items}


@app.post("/ltv/calculate")
def calculate_ltv(payload: Dict[str, Any] = Body(...)) -> Dict[str, float]:
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
    ltv = float(loan_amount) / float(collateral_value)
    return {"ltv": ltv}


@app.post("/collateral/reset")
def reset_collateral() -> Dict[str, str]:
    """Reset the in-memory collateral registry and addresses for test isolation."""
    collateral_registry.clear()
    registered_addresses.clear()
    return {"status": "reset"}
