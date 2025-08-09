"""Tests for treasury_orchestrator.models module."""

import json
from datetime import datetime, timezone
from decimal import Decimal

import pytest

from treasury_orchestrator.models import RiskChecks, SweepOrder


def test_risk_checks_creation():
    """Test RiskChecks model creation."""
    risk_checks = RiskChecks(var_limit_bps=10, observed_var_bps=5)
    assert risk_checks.var_limit_bps == 10
    assert risk_checks.observed_var_bps == 5


def test_sweep_order_creation():
    """Test SweepOrder model creation."""
    now = datetime.now(tz=timezone.utc)
    risk_checks = RiskChecks(var_limit_bps=10, observed_var_bps=5)

    order = SweepOrder(
        order_id="test_order_123",
        source_account="0123456789",
        target_product="FED_RRP",
        amount_usd=Decimal("10000.0000"),
        cutoff_utc=now,
        risk_checks=risk_checks,
        created_ts=now,
    )

    assert order.order_id == "test_order_123"
    assert order.source_account == "0123456789"
    assert order.target_product == "FED_RRP"
    assert order.amount_usd == Decimal("10000.0000")
    assert order.cutoff_utc == now
    assert order.risk_checks == risk_checks
    assert order.created_ts == now


def test_sweep_order_json_serialization():
    """Test that SweepOrder can be serialized to JSON properly."""
    now = datetime.now(tz=timezone.utc)
    risk_checks = RiskChecks(var_limit_bps=10, observed_var_bps=5)

    order = SweepOrder(
        order_id="test_order_123",
        source_account="0123456789",
        target_product="FED_RRP",
        amount_usd=Decimal("10000.0000"),
        cutoff_utc=now,
        risk_checks=risk_checks,
        created_ts=now,
    )

    # Test that model_dump_json() works
    if hasattr(order, "model_dump_json"):
        json_str = order.model_dump_json(indent=2)
    else:
        import json as _json

        json_str = _json.dumps(
            order.dict(exclude={"model_config"}), default=str, indent=2
        )
    assert isinstance(json_str, str)

    # Test that we can parse it back
    parsed = json.loads(json_str)
    assert parsed["order_id"] == "test_order_123"
    assert parsed["amount_usd"] == "10000.0000"
    assert parsed["risk_checks"]["var_limit_bps"] == 10


def test_sweep_order_schema_compliance():
    """Test that SweepOrder output matches the expected schema structure."""
    now = datetime.now(tz=timezone.utc)
    risk_checks = RiskChecks(var_limit_bps=10, observed_var_bps=5)

    order = SweepOrder(
        order_id="test_order_123",
        source_account="0123456789",
        target_product="FED_RRP",
        amount_usd=Decimal("10000.0000"),
        cutoff_utc=now,
        risk_checks=risk_checks,
        created_ts=now,
    )

    data = order.model_dump() if hasattr(order, "model_dump") else order.dict()

    # Check all required fields are present
    required_fields = [
        "order_id",
        "source_account",
        "target_product",
        "amount_usd",
        "cutoff_utc",
        "risk_checks",
        "created_ts",
    ]
    for field in required_fields:
        assert field in data

    # Check risk_checks structure
    assert "var_limit_bps" in data["risk_checks"]
    assert "observed_var_bps" in data["risk_checks"]
