import importlib.util

import pytest

HTTPX_AVAILABLE = importlib.util.find_spec("httpx") is not None
pytestmark = pytest.mark.skipif(not HTTPX_AVAILABLE, reason="httpx not installed")

if HTTPX_AVAILABLE:
    from fastapi.testclient import TestClient

    from mocks.mock_finastra_api import app

    client = TestClient(app)


def test_ltv_calculate_valid():
    response = client.post(
        "/ltv/calculate", json={"collateral_value": 100000, "loan_amount": 80000}
    )
    assert response.status_code == 200
    data = response.json()
    assert "ltv" in data
    assert data["ltv"] == 0.8


def test_ltv_calculate_missing_fields():
    response = client.post("/ltv/calculate", json={"collateral_value": 100000})
    assert response.status_code == 400
    assert "Missing collateral_value or loan_amount" in response.text


def test_ltv_calculate_non_numeric():
    response = client.post(
        "/ltv/calculate", json={"collateral_value": "abc", "loan_amount": 50000}
    )
    assert response.status_code == 400
    assert "Values must be numeric" in response.text


def test_ltv_calculate_zero_collateral():
    response = client.post(
        "/ltv/calculate", json={"collateral_value": 0, "loan_amount": 50000}
    )
    assert response.status_code == 400
    assert "collateral_value must be positive" in response.text
