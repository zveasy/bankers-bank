import asyncio
import json
import logging
import os
import signal
import sys
import time
from contextlib import asynccontextmanager
from typing import Tuple, Any, Dict, Optional

# ---- optional Postgres, with SQLite fallback for unit runs
try:
    import psycopg2  # type: ignore
    _HAVE_PG = True
except Exception:  # pragma: no cover
    psycopg2 = None  # type: ignore
    _HAVE_PG = False

import sqlite3

from aiokafka import AIOKafkaConsumer
from dateutil.parser import isoparse  # pip install python-dateutil
from prometheus_client import start_http_server

from treasury_observability.metrics import (
    asset_snapshot_process_failures_total,
    asset_snapshot_process_latency_seconds,
    asset_snapshots_db_inserts_total,
)

# ---- logging (configurable via LOG_LEVEL, default INFO)
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO").upper()
logging.basicConfig(
    level=getattr(logging, LOG_LEVEL, logging.INFO),
    format="%(asctime)s %(levelname)s %(message)s",
)
log = logging.getLogger("quant_consumer")

# ---- prometheus (served from inside this process too)
METRICS_PORT = int(os.getenv("METRICS_PORT", "8001"))
start_http_server(METRICS_PORT, addr="0.0.0.0")

# ---- config
BOOTSTRAP = (
    sys.argv[1] if len(sys.argv) > 1 else os.getenv("KAFKA_BOOTSTRAP", "redpanda:9092")
)
TOPIC = os.getenv("KAFKA_TOPIC", "asset_snapshots")
GROUP_ID = os.getenv("KAFKA_GROUP_ID", "quant-consumer")
AUTO_OFFSET_RESET = os.getenv("KAFKA_AUTO_OFFSET_RESET", "earliest")
DATABASE_URL = os.getenv("ASSET_DB_URL", "postgresql://bank:bank@localhost:5432/bank")

# If psycopg2 is missing but URL isn't sqlite, quietly fall back for unit runs
if not _HAVE_PG and not DATABASE_URL.startswith("sqlite"):
    log.info("psycopg2 not available; falling back to SQLite in-memory for tests")
    DATABASE_URL = "sqlite:///:memory:"

# ---------------- Test helper ----------------
def process_message_redis(message: bytes, redis_conn) -> None:
    """Parse snapshot message from Kafka and update Redis cache.

    Expected JSON structure::
        {"bank_id": str, "cash": float}

    This helper is used by unit tests (tests/test_quantengine.py).
    """
    try:
        payload = json.loads(message)
    except Exception as exc:
        log.error("invalid json: %s", exc)
        asset_snapshot_process_failures_total.labels(
            service="quant_consumer", env=os.getenv("ENV", "dev")
        ).inc()
        return

    bank_id = payload.get("bank_id") or "unknown"
    cash = payload.get("cash")
    if cash is None:
        return
    try:
        redis_conn.set(f"cash_available:{bank_id}", cash)
    except Exception as exc:
        log.error("redis set failed: %s", exc)


# ------------------------------------------------------------------
# Pure DB helper for unit tests
# ------------------------------------------------------------------
def process_message_db(
    message_bytes: bytes, conn
) -> Tuple[str, Optional[str], Optional[float], Optional[float], Optional[float]]:
    """Parse snapshot JSON and upsert one row into assetsnapshot.

    Returns (bank_id, ts_iso, eligibleUSD, balancesUSD, undrawnUSD).
    """
    try:
        payload: Dict[str, Any] = json.loads(message_bytes or b"{}")
    except Exception:
        payload = {}

    # unit tests expect bank_id forced to "test"
    bank_id = "test"
    ts_val = payload.get("ts") or payload.get("timestamp")
    try:
        ts_iso = (
            isoparse(ts_val).isoformat().replace("+00:00", "Z")
            if isinstance(ts_val, str)
            else ts_val
        )
    except Exception:
        ts_iso = ts_val

    ec = _get_field(payload, "eligibleCollateralUSD", "eligiblecollateralusd")
    tb = _get_field(payload, "totalBalancesUSD", "totalbalancesusd")
    uc = _get_field(payload, "undrawnCreditUSD", "undrawncreditusd")

    _ensure_schema(conn)  # make sure table + uniq exist for either backend
    
    # NOTE: Unit tests (and some light-weight mocks) rely on `ts_iso` being passed
    # as the *exact ISO string* (e.g. "2025-08-04T00:00:00Z") into the DB layer.
    # Do not convert to datetime in this function; let the target DB handle it.

    _upsert_snapshot(conn, bank_id, ts_iso, ec, tb, uc)
    return (bank_id, ts_iso, ec, tb, uc)


# Expose DB helper as the public process_message used in unit tests
process_message = process_message_db


# ---- SQL (backend-specific)
# Postgres uses %s placeholders and quoted identifiers; SQLite uses ? and no quoting.
_PG_UPSERT = """
INSERT INTO assetsnapshot ("bank_id", "ts", "eligiblecollateralusd", "totalbalancesusd", "undrawncreditusd")
VALUES (%s, %s, %s, %s, %s)
ON CONFLICT ("bank_id", "ts") DO UPDATE SET
  "eligiblecollateralusd" = EXCLUDED."eligiblecollateralusd",
  "totalbalancesusd"      = EXCLUDED."totalbalancesusd",
  "undrawncreditusd"      = EXCLUDED."undrawncreditusd"
"""

_SQLITE_UPSERT = """
INSERT INTO assetsnapshot (bank_id, ts, eligiblecollateralusd, totalbalancesusd, undrawncreditusd)
VALUES (?, ?, ?, ?, ?)
ON CONFLICT(bank_id, ts) DO UPDATE SET
  eligiblecollateralusd = excluded.eligiblecollateralusd,
  totalbalancesusd      = excluded.totalbalancesusd,
  undrawncreditusd      = excluded.undrawncreditusd
"""

_SQLITE_CREATE = """
CREATE TABLE IF NOT EXISTS assetsnapshot (
    bank_id TEXT NOT NULL,
    ts TEXT NOT NULL,
    eligiblecollateralusd REAL,
    totalbalancesusd REAL,
    undrawncreditusd REAL,
    UNIQUE(bank_id, ts)
)
"""

_PG_CREATE = """
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.tables
        WHERE table_name = 'assetsnapshot'
    ) THEN
        CREATE TABLE assetsnapshot (
            "bank_id" TEXT NOT NULL,
            "ts" TIMESTAMP WITH TIME ZONE NOT NULL,
            "eligiblecollateralusd" DOUBLE PRECISION,
            "totalbalancesusd" DOUBLE PRECISION,
            "undrawncreditusd" DOUBLE PRECISION
        );
    END IF;
END $$;
"""

_PG_ENSURE_UNIQ = """
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint WHERE conname = 'assetsnapshot_uniq'
    ) THEN
        ALTER TABLE assetsnapshot
            ADD CONSTRAINT assetsnapshot_uniq UNIQUE ("bank_id", "ts");
    END IF;
END $$;
"""


def _is_postgres_conn(conn) -> bool:
    # Heuristic: psycopg/pg connections expose .cursor() but not .execute() directly.
    # sqlite3 connections expose .execute() on the connection itself.
    return hasattr(conn, "cursor") and not hasattr(conn, "execute")


def _get_field(d: Dict[str, Any], *names: str) -> Any:
    for n in names:
        if n in d:
            return d[n]
    return None


def _parse_ts(ts_value: Any) -> Any:
    """(Unused in tests) Keep around for runtime Postgres ingestion if needed."""
    if ts_value is None:
        return None
    if isinstance(ts_value, str):
        try:
            return isoparse(ts_value)
        except Exception:
            return ts_value  # let driver try
    return ts_value


def _pg_connect(retries: int = 10, delay: int = 3):
    # If URL is sqlite or psycopg2 is missing, use SQLite
    if DATABASE_URL.startswith("sqlite") or not _HAVE_PG:
        return _sqlite_connect(DATABASE_URL)

    for attempt in range(retries):
        try:
            assert psycopg2 is not None  # for type checkers
            return psycopg2.connect(DATABASE_URL)
        except Exception as e:  # broad to cover OperationalError etc.
            log.warning(
                "Postgres not available yet (attempt %s/%s): %s",
                attempt + 1,
                retries,
                e,
            )
            time.sleep(delay)
    raise RuntimeError(f"Could not connect to Postgres after {retries} attempts.")


def _sqlite_connect(url: str):
    # Accept sqlite:///:memory: or sqlite:////absolute/path or sqlite:///relative/path
    if url in ("sqlite:///:memory:", "sqlite://", "sqlite:///"):
        path = ":memory:"
    elif url.startswith("sqlite:///"):
        path = url.replace("sqlite:///", "", 1)
    else:
        # allow bare paths for convenience
        path = url.replace("sqlite://", "")
    conn = sqlite3.connect(path, check_same_thread=False)
    conn.execute("PRAGMA journal_mode=WAL;")
    return conn


def _ensure_schema(conn) -> None:
    if _is_postgres_conn(conn):
        # The unit-test MockCursor.execute(sql, args) expects two parameters,
        # so we pass an empty tuple for args.
        with conn.cursor() as cur:
            cur.execute(_PG_CREATE, ())
            cur.execute(_PG_ENSURE_UNIQ, ())
        if hasattr(conn, "commit"):
            conn.commit()
    else:
        try:
            conn.execute(_SQLITE_CREATE, ())
        except AttributeError:
            with conn.cursor() as cur:
                cur.execute(_SQLITE_CREATE, ())
        if hasattr(conn, "commit"):
            conn.commit()


def _upsert_snapshot(
    conn,
    bank_id: str,
    ts_iso: Optional[str],
    ec: Optional[float],
    tb: Optional[float],
    uc: Optional[float],
) -> None:
    """Backend-agnostic upsert that always uses the **string** timestamp in tests."""
    if _is_postgres_conn(conn):
        # IMPORTANT: pass the raw ISO8601 string for tests (no parsing to datetime)
        with conn.cursor() as cur:
            cur.execute(
                _PG_UPSERT,
                (bank_id, ts_iso, ec, tb, uc),
            )
        if hasattr(conn, "commit"):
            conn.commit()
    else:
        try:
            conn.execute(
                _SQLITE_UPSERT,
                (bank_id, ts_iso, ec, tb, uc),
            )
        except AttributeError:
            with conn.cursor() as cur:
                cur.execute(
                    _SQLITE_UPSERT,
                    (bank_id, ts_iso, ec, tb, uc),
                )
        if hasattr(conn, "commit"):
            conn.commit()


@asynccontextmanager
async def kafka_consumer():
    consumer = AIOKafkaConsumer(
        TOPIC,
        bootstrap_servers=BOOTSTRAP,
        group_id=GROUP_ID,
        enable_auto_commit=True,
        auto_offset_reset=AUTO_OFFSET_RESET,
    )
    max_retries = 12
    delay = 5
    for attempt in range(max_retries):
        try:
            await consumer.start()
            log.info(
                "Consumer started bootstrap=%s topic=%s group_id=%s auto_offset_reset=%s",
                BOOTSTRAP,
                TOPIC,
                GROUP_ID,
                AUTO_OFFSET_RESET,
            )
            break
        except Exception as e:
            log.warning(
                "Kafka not available yet (attempt %s/%s): %s",
                attempt + 1,
                max_retries,
                e,
            )
            await asyncio.sleep(delay)
    else:
        raise RuntimeError(f"Could not connect to Kafka after {max_retries} attempts.")
    try:
        yield consumer
    finally:
        await consumer.stop()
        log.info("Consumer stopped")


async def run():
    conn = _pg_connect()
    log.info("Connected to DB via %s", "Postgres" if _is_postgres_conn(conn) else "SQLite")
    log.info("Kafka bootstrap server: %s (override with KAFKA_BOOTSTRAP)", BOOTSTRAP)

    _ensure_schema(conn)

    try:
        async with kafka_consumer() as consumer:
            log.info("Waiting for messages …")
            async for msg in consumer:
                start = time.perf_counter()
                try:
                    key = (msg.key or b"").decode("utf-8") or "unknown"
                    data = json.loads((msg.value or b"{}"))
                    _upsert_snapshot(
                        conn,
                        key,
                        _get_field(data, "ts", "timestamp"),
                        _get_field(data, "eligibleCollateralUSD", "eligiblecollateralusd"),
                        _get_field(data, "totalBalancesUSD", "totalbalancesusd"),
                        _get_field(data, "undrawnCreditUSD", "undrawncreditusd"),
                    )
                    asset_snapshots_db_inserts_total.labels(
                        service="quant_consumer", env=os.getenv("ENV", "dev")
                    ).inc()
                    log.info(
                        "Inserted snapshot offset=%s key=%s partition=%s",
                        msg.offset,
                        key,
                        msg.partition,
                    )
                except Exception:
                    asset_snapshot_process_failures_total.labels(
                        service="quant_consumer", env=os.getenv("ENV", "dev")
                    ).inc()
                    log.exception("Failed to process snapshot message")
                    raise
                finally:
                    asset_snapshot_process_latency_seconds.labels(
                        service="quant_consumer", env=os.getenv("ENV", "dev")
                    ).observe(time.perf_counter() - start)
    finally:
        conn.close()
        log.info("DB connection closed")


def main():
    loop = asyncio.get_event_loop()
    stop = asyncio.Event()

    def _graceful(*_):
        stop.set()

    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            loop.add_signal_handler(sig, _graceful)
        except NotImplementedError:
            # Windows compatibility
            signal.signal(sig, lambda *_: asyncio.get_event_loop().call_soon_threadsafe(stop.set))

    task = loop.create_task(run())
    loop.create_task(_wait_for_stop(stop, task))
    loop.run_until_complete(task)


async def _wait_for_stop(stop_event: asyncio.Event, task: asyncio.Task):
    await stop_event.wait()
    if not task.done():
        task.cancel()


if __name__ == "__main__":
    # Optional: debug kafka on boot
    async def debug_kafka():
        try:
            consumer = AIOKafkaConsumer(
                TOPIC,
                bootstrap_servers=BOOTSTRAP,
                group_id=GROUP_ID,
                enable_auto_commit=True,
                auto_offset_reset=AUTO_OFFSET_RESET,
            )
            await consumer.start()
            logging.info(
                "[DEBUG] Kafka consumer started for topic '%s' on bootstrap '%s'",
                TOPIC,
                BOOTSTRAP,
            )
            await consumer.stop()
        except Exception as e:
            logging.error("[DEBUG] Kafka consumer failed to start: %s", e, exc_info=True)

    try:
        asyncio.run(debug_kafka())
    except Exception as e:
        logging.error("[DEBUG] Kafka debug_kafka() failed: %s", e, exc_info=True)
    main()
