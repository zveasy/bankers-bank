import json
import pytest
import types

try:
    from fastapi.testclient import TestClient
    import httpx
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
    from quantengine.main import app, redis_client
    from quantengine.kafka_consumer import process_message
    from quantengine.db import engine, init_db, CashPosition
    from sqlmodel import Session


def setup_function():
    redis_client.flushdb()
    init_db()


def test_process_message_updates_redis():
    r = fakeredis.FakeRedis()
    message = json.dumps({"bank_id": "b1", "cash": 50.5}).encode()
    process_message(message, r)
    assert r.get("cash_available:b1") == b"50.5"


def test_investable_cash_endpoint_reads_redis(tmp_path):
    client = TestClient(app)
    redis_client.set("cash_available:b2", 70)
    resp = client.get("/investable-cash", params={"bank_id": "b2"})
    assert resp.status_code == 200
    assert resp.json() == {"cash": 70.0}


def test_investable_cash_fallback_db(monkeypatch):
    client = TestClient(app)
    redis_client.flushdb()
    with Session(engine) as session:
        session.add(CashPosition(bank_id="b3", cash=99.9))
        session.commit()
    resp = client.get("/investable-cash", params={"bank_id": "b3"})
    assert resp.status_code == 200
    assert resp.json() == {"cash": 99.9}
