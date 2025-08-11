"""Offline tests for Liquidity API endpoints.

These tests ensure no network/Kafka dependency. They rely on the router being
included either in quantengine.main.app or exposed via create_app()."""
from __future__ import annotations

import os
from typing import List

import pytest
from fastapi.testclient import TestClient


# ---------------------------------------------------------------------------
# Helper to get the FastAPI app
# ---------------------------------------------------------------------------

def _get_app():
    """Import the FastAPI app with fallback for local router-only build."""
    try:
        from quantengine.main import app  # type: ignore

        return app
    except Exception:
        # Fallback to a standalone app factory in the liquidity API
        try:
            from quantengine.liquidity.api import create_app  # type: ignore

            return create_app()
        except Exception as exc:  # pragma: no cover
            raise RuntimeError("FastAPI app not found for Liquidity API tests") from exc


@pytest.fixture(scope="module")
def client() -> TestClient:
    return TestClient(_get_app())


# ---------------------------------------------------------------------------
# Utilities
# ---------------------------------------------------------------------------

def _metrics_text(client: TestClient) -> str:
    r = client.get("/metrics")
    assert r.status_code == 200
    return r.text


# ---------------------------------------------------------------------------
# Tests – /liquidity/evaluate
# ---------------------------------------------------------------------------

def test_evaluate_happy_path(client: TestClient):
    payload = {
        "bank_id": "bank1",
        "available_cash_usd": 100_000.0,
        "asof_ts": "2025-08-06T10:37:01Z",
        "policy": {
            "min_cash_bps": 100,  # 1%
            "max_draw_bps": 5_000,  # 50%
            "settlement_calendar": [],
        },
    }

    resp = client.post("/liquidity/evaluate", json=payload)
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert set(body.keys()) >= {"ok", "reasons", "allowed_draw_usd", "buffer_usd"}
    assert body["ok"] is True
    # buffer should be <= available
    assert 0 <= body["buffer_usd"] <= payload["available_cash_usd"]

    m_text = _metrics_text(client)
    assert "liquidity_buffer_usd" in m_text and 'bank_id="bank1"' in m_text


def test_evaluate_violation_records_counter(client: TestClient):
    payload = {
        "bank_id": "bank2",
        "available_cash_usd": 10_000.0,
        "requested_draw_usd": 9_900.0,
        "asof_ts": "2025-08-06T10:37:01Z",
        "policy": {
            "min_cash_bps": 10_000,  # 100% buffer – ensures min_buffer violation
            "max_draw_bps": 0,  # no draws allowed – max_draw_cap violation
            "settlement_calendar": [],
        },
    }

    resp = client.post("/liquidity/evaluate", json=payload)
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["ok"] is False
    assert len(body["reasons"]) >= 1

    m_text = _metrics_text(client)
    assert "policy_violations_total" in m_text


# ---------------------------------------------------------------------------
# Tests – /bridge/publish
# ---------------------------------------------------------------------------

def test_publish_dry_run_increments_metrics(client: TestClient, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("QUANT_DRY_RUN", "1")
    payload = {
        "bank_id": "bank3",
        "asof_ts": "2025-08-06T10:37:01Z",
        "available_cash_usd": 250_000.0,
        "reserved_buffer_usd": 25_000.0,
        "notes": "unit-test",
    }
    resp = client.post("/bridge/publish", json=payload)
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body.get("ok") is True
    assert body.get("dry_run") is True
    assert body.get("key")

    m_text = _metrics_text(client)
    assert "quant_publish_total" in m_text
    assert "quant_publish_latency_seconds" in m_text
