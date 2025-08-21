import json
import types

import pytest

try:
    import httpx
    from fastapi.testclient import TestClient

    HTTPX_AVAILABLE = True
except Exception:
    HTTPX_AVAILABLE = False

try:
    import fakeredis

    FAKEREDIS_AVAILABLE = True
except Exception:
    FAKEREDIS_AVAILABLE = False

try:
    import redis as _redis

    REDIS_AVAILABLE = True
except Exception:
    REDIS_AVAILABLE = False

pytestmark = pytest.mark.skipif(
    not HTTPX_AVAILABLE or not FAKEREDIS_AVAILABLE or not REDIS_AVAILABLE,
    reason="required libraries not installed",
)

if REDIS_AVAILABLE:
    from sqlmodel import Session

    from quantengine.db import CashPosition, engine, init_db
    from quantengine.kafka_consumer import process_message
    from quantengine.main import app, redis_client


def setup_function():
    redis_client.flushdb()
    init_db()


def test_process_message_updates_redis():
    import types

    class MockCursor:
        def __init__(self):
            self.last_args = None

        def execute(self, sql, args):
            self.last_args = args

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc_val, exc_tb):
            pass

    class MockConn:
        def __init__(self):
            self.cursor_obj = MockCursor()
            self.committed = False

        def cursor(self):
            return self.cursor_obj

        def commit(self):
            self.committed = True

    message = json.dumps(
        {
            "bank_id": "b1",
            "ts": "2025-08-04T00:00:00Z",
            "eligibleCollateralUSD": 50.5,
            "totalBalancesUSD": 100.0,
            "undrawnCreditUSD": 10.0,
        }
    ).encode()
    conn = MockConn()
    process_message(message, conn)
    # Check that the correct values were passed to the DB
    assert conn.cursor_obj.last_args[0] == "test"
    assert conn.cursor_obj.last_args[1] == "2025-08-04T00:00:00Z"
    assert conn.cursor_obj.last_args[2] == 50.5


def test_investable_cash_endpoint_reads_redis(tmp_path):
    client = TestClient(app)
    redis_client.set("cash_available:b2", 70)
    resp = client.get(
        "/investable-cash",
        params={"bank_id": "b2"},
        headers={"Authorization": "Bearer testtoken"},
    )
    assert resp.status_code == 200
    assert resp.json() == {"cash": 70.0}


def test_investable_cash_fallback_db(monkeypatch):
    client = TestClient(app)
    redis_client.flushdb()
    with Session(engine) as session:
        session.add(CashPosition(bank_id="b3", cash=99.9))
        session.commit()
    resp = client.get(
        "/investable-cash",
        params={"bank_id": "b3"},
        headers={"Authorization": "Bearer testtoken"},
    )
    assert resp.status_code == 200
    assert resp.json() == {"cash": 99.9}


def test_investable_cash_unauthorized():
    client = TestClient(app)
    r = client.get("/investable-cash", params={"bank_id": "b2"})
    assert r.status_code == 401
