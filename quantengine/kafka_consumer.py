# quantengine/kafka_consumer.py
import asyncio
import json
import logging
import os
import signal
import sys
from contextlib import asynccontextmanager

import psycopg2
import time
from treasury_observability.metrics import (
    asset_snapshots_db_inserts_total,
    asset_snapshot_process_failures_total,
    asset_snapshot_process_latency_seconds,
)
from aiokafka import AIOKafkaConsumer, TopicPartition
from prometheus_client import Counter, Histogram, start_http_server

# ---- logging (configurable via LOG_LEVEL, default INFO)
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO").upper()
logging.basicConfig(
    level=getattr(logging, LOG_LEVEL, logging.INFO),
    format="%(asctime)s %(levelname)s %(message)s",
)
log = logging.getLogger("quant_consumer")

# ---- prometheus (served from inside this process too)
METRICS_PORT = int(os.getenv("METRICS_PORT", "8001"))  # optional; keep consistent with others
start_http_server(METRICS_PORT, addr="0.0.0.0")  # <-- important for Prometheus scraping

# ---- config
BOOTSTRAP = sys.argv[1] if len(sys.argv) > 1 else os.getenv("KAFKA_BOOTSTRAP", "redpanda:9092")
TOPIC = os.getenv("KAFKA_TOPIC", "asset_snapshots")
GROUP_ID = os.getenv("KAFKA_GROUP_ID", "quant-consumer")
AUTO_OFFSET_RESET = os.getenv("KAFKA_AUTO_OFFSET_RESET", "earliest")

# Use 'localhost' for default Postgres hostname to avoid container DNS issues in local/dev
DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://bank:bank@localhost:5432/bank")

def _pg_connect(retries=10, delay=3):
    import time
    for attempt in range(retries):
        try:
            return psycopg2.connect(DATABASE_URL)
        except psycopg2.OperationalError as e:
            log.warning(f"Postgres not available yet (attempt {attempt+1}/{retries}): {e}")
            time.sleep(delay)
    raise psycopg2.OperationalError(f"Could not connect to Postgres after {retries} attempts.")

def _ensure_snapshot_uniqueness(conn):
    with conn.cursor() as cur:
        cur.execute("""
            DO $$
            BEGIN
                IF NOT EXISTS (
                    SELECT 1
                    FROM pg_constraint
                    WHERE conname = 'assetsnapshot_uniq'
                ) THEN
                    ALTER TABLE assetsnapshot
                      ADD CONSTRAINT assetsnapshot_uniq UNIQUE ("bank_id", "ts");
                END IF;
            END
            $$;
        """)
    conn.commit()

def _insert_snapshot(conn, bank_id: str, payload: dict):
    with conn.cursor() as cur:
        cur.execute(
            '''
            INSERT INTO assetsnapshot ("bank_id", "ts", "eligibleCollateralUSD", "totalBalancesUSD", "undrawnCreditUSD")
            VALUES (%s, %s, %s, %s, %s)
            ON CONFLICT ("bank_id", "ts") DO UPDATE SET
              "eligibleCollateralUSD" = EXCLUDED."eligibleCollateralUSD",
              "totalBalancesUSD"      = EXCLUDED."totalBalancesUSD",
              "undrawnCreditUSD"      = EXCLUDED."undrawnCreditUSD"
            ''' ,
            (
                bank_id,
                payload["ts"],
                payload["eligibleCollateralUSD"],
                payload["totalBalancesUSD"],
                payload["undrawnCreditUSD"],
            ),
        )
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
                BOOTSTRAP, TOPIC, GROUP_ID, AUTO_OFFSET_RESET,
            )
            break
        except Exception as e:
            log.warning(f"Kafka not available yet (attempt {attempt+1}/{max_retries}): {e}")
            await asyncio.sleep(delay)
    else:
        raise RuntimeError(f"Could not connect to Kafka after {max_retries} attempts.")
    try:
        yield consumer
    finally:
        await consumer.stop()
        log.info("Consumer stopped")

async def run():
    # DB connection
    conn = _pg_connect()
    log.info("Connected to Postgres")
    log.info(f"Kafka bootstrap server: {BOOTSTRAP} (override with KAFKA_BOOTSTRAP env var)")
    _ensure_snapshot_uniqueness(conn)
    try:
        async with kafka_consumer() as consumer:
            log.info("Waiting for messages …")
            async for msg in consumer:
                start = time.perf_counter()
                try:
                    key = (msg.key or b"").decode("utf-8") or "unknown"
                    data = json.loads((msg.value or b"{}"))
                    sql = (
                        'INSERT INTO assetsnapshot ("bank_id", "ts", "eligibleCollateralUSD", "totalBalancesUSD", "undrawnCreditUSD") '
                        'VALUES (%s, %s, %s, %s, %s) '
                        'ON CONFLICT ("bank_id", "ts") DO UPDATE SET '
                        '"eligibleCollateralUSD" = EXCLUDED."eligibleCollateralUSD", '
                        '"totalBalancesUSD" = EXCLUDED."totalBalancesUSD", '
                        '"undrawnCreditUSD" = EXCLUDED."undrawnCreditUSD"'
                    )
                    def get_field(d, *names):
                        for n in names:
                            if n in d:
                                return d[n]
                        return None
                    with conn.cursor() as cur:
                        cur.execute(sql, (
                            key,
                            get_field(data, "ts", "timestamp"),
                            get_field(data, "eligibleCollateralUSD", "eligible_collateral_usd"),
                            get_field(data, "totalBalancesUSD", "total_balances_usd"),
                            get_field(data, "undrawnCreditUSD", "undrawn_credit_usd"),
                        ))
                    conn.commit()
                    asset_snapshots_db_inserts_total.labels(service="quant_consumer", env=os.getenv("ENV", "dev")).inc()
                    log.info(
                        "Inserted snapshot offset=%s key=%s partition=%s",
                        msg.offset, key, msg.partition
                    )
                except Exception:
                    asset_snapshot_process_failures_total.labels(service="quant_consumer", env=os.getenv("ENV", "dev")).inc()
                    log.exception("Failed to process snapshot message")
                    raise
                finally:
                    asset_snapshot_process_latency_seconds.labels(service="quant_consumer", env=os.getenv("ENV", "dev")).observe(time.perf_counter() - start)
    finally:
        conn.close()
        log.info("Postgres connection closed")

def main():
    loop = asyncio.get_event_loop()
    stop = asyncio.Event()

    def _graceful(*_):
        stop.set()

    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            loop.add_signal_handler(sig, _graceful)
        except NotImplementedError:
            # Windows
            signal.signal(sig, lambda *_: _graceful())

    task = loop.create_task(run())
    loop.create_task(_wait_for_stop(stop, task))
    loop.run_until_complete(task)

async def _wait_for_stop(stop_event: asyncio.Event, task: asyncio.Task):
    await stop_event.wait()
    if not task.done():
        task.cancel()

if __name__ == "__main__":
    # DEBUG: Test aiokafka connectivity and log metadata errors before main consumer loop
    import logging
    from aiokafka import AIOKafkaConsumer
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
            logging.info(f"[DEBUG] Kafka consumer started successfully for topic '{TOPIC}' on bootstrap '{BOOTSTRAP}'")
            await consumer.stop()
        except Exception as e:
            logging.error(f"[DEBUG] Kafka consumer failed to start: {e}", exc_info=True)
    try:
        asyncio.run(debug_kafka())
    except Exception as e:
        logging.error(f"[DEBUG] Kafka debug_kafka() failed: {e}", exc_info=True)
    # Continue with normal main loop
    main()
