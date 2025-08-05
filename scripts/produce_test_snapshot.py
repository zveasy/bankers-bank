import asyncio
import json
from aiokafka import AIOKafkaProducer
import os
from datetime import datetime

KAFKA_BOOTSTRAP = os.getenv("KAFKA_BOOTSTRAP", "localhost:29092")
TOPIC = "asset_snapshots"

async def produce():
    producer = AIOKafkaProducer(bootstrap_servers=KAFKA_BOOTSTRAP)
    try:
        await producer.start()
    except Exception as e:
        print(f"ERROR: Could not connect to Kafka at {KAFKA_BOOTSTRAP}. Is Redpanda running and port 9092 exposed to host?\n{e}")
        return
    try:
        payload = {
            "bank_id": "demo-bank",
            "ts": datetime.utcnow().isoformat() + "Z",
            "eligibleCollateralUSD": 123.45,
            "totalBalancesUSD": 678.90,
            "undrawnCreditUSD": 50.00
        }
        value = json.dumps(payload).encode("utf-8")
        key = payload["bank_id"].encode("utf-8")
        result = await producer.send_and_wait(TOPIC, value=value, key=key)
        print(f"Produced to partition {result.partition} at offset {result.offset}")
    finally:
        await producer.stop()

if __name__ == "__main__":
    asyncio.run(produce())
