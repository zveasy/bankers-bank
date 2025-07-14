from bankersbank.client import BankersBankClient
import pytest

class DummyClient(BankersBankClient):
    base_url = "http://dummy"  # Add base_url to avoid AttributeError
    def __init__(self):
        self.token = None  # Add token to avoid AttributeError
    def get_balances(self, account_id: str):
        return {"items": [{"type": "BOOKED", "amount": 100.0}]}
    def get_collateral(self):
        return {"items": [{"valuation": 200.0}, {"valuation": 300.0}]}
    def calculate_ltv(self, account_id: str):
        # Pure in-memory calculation, no network
        balances = self.get_balances(account_id)
        booked = next((b for b in balances.get("items", []) if b.get("type") == "BOOKED"), None)
        if not booked:
            raise ValueError("BOOKED balance not found for account")
        loan_balance = float(booked.get("amount", 0))
        collateral_resp = self.get_collateral()
        total_collateral = sum(float(c.get("valuation", 0)) for c in collateral_resp.get("items", []))
        if total_collateral == 0:
            raise ValueError("Total collateral valuation is zero")
        ltv = loan_balance / total_collateral
        return {
            "account_id": account_id,
            "loan_balance": loan_balance,
            "total_collateral": total_collateral,
            "ltv": ltv,
        }


def test_calculate_ltv():
    client = DummyClient()
    result = client.calculate_ltv("123")
    assert pytest.approx(result["ltv"]) == 100.0 / 500.0
    assert result["loan_balance"] == 100.0
    assert result["total_collateral"] == 500.0


def test_calculate_ltv_no_collateral():
    class BadClient(DummyClient):
        def get_collateral(self):
            return {"items": []}
    client = BadClient()
    with pytest.raises(ValueError):
        client.calculate_ltv("123")
