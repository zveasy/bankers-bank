from bankersbank.client import BankersBankClient
import pytest

class DummyClient(BankersBankClient):
    def __init__(self):
        pass
    def get_balances(self, account_id: str):
        return {"items": [{"type": "BOOKED", "amount": 100.0}]}
    def get_collateral(self):
        return {"items": [{"valuation": 200.0}, {"valuation": 300.0}]}


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
