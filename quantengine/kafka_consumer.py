import json
import os
from kafka import KafkaConsumer
import redis

REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")


def process_message(raw: bytes, r: redis.Redis | None = None) -> None:
    data = json.loads(raw.decode())
    bank_id = data.get("bank_id")
    cash = data.get("cash")
    if bank_id is None or cash is None:
        return
    r = r or redis.Redis.from_url(REDIS_URL)
    r.set(f"cash_available:{bank_id}", cash)


def run_consumer(broker: str = "localhost:9092") -> None:
    consumer = KafkaConsumer(
        "treasury.positions.v1",
        bootstrap_servers=[broker],
        value_deserializer=lambda m: m,
    )
    r = redis.Redis.from_url(REDIS_URL)
    for msg in consumer:
        process_message(msg.value, r)
