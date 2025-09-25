import json
import sqlite3
from typing import Any, Dict, Tuple
from quantengine.kafka_consumer import process_message_db, _ensure_schema

def _mk_sqlite():
    conn = sqlite3.connect(":memory:", check_same_thread=False)
    _ensure_schema(conn)
    return conn

def test_ts_is_stored_as_exact_iso_string_sqlite():
    conn = _mk_sqlite()
    msg = json.dumps({
        "bank_id": "ignored-by-test",  # overridden to "test"
        "ts": "2025-08-04T00:00:00Z",
        "eligibleCollateralUSD": 1.2,
        "totalBalancesUSD": 3.4,
        "undrawnCreditUSD": 5.6,
    }).encode()

    bank_id, ts_iso, *_ = process_message_db(msg, conn)
    # The helper returns what it wrote; assert exact string preservation
    assert bank_id == "test"
    assert ts_iso == "2025-08-04T00:00:00Z"

    # And double-check what’s actually in the DB
    cur = conn.execute("SELECT bank_id, ts FROM assetsnapshot")
    row = cur.fetchone()
    assert row == ("test", "2025-08-04T00:00:00Z")
    conn.close()
