"""Quick smoke test for Quantengine liquidity endpoints.

This script assumes the quantengine service is running locally (docker compose)
and reachable at https://127.0.0.1:9100.
"""
from __future__ import annotations

import os
import sys
import time
from typing import Final

import requests

BASE: Final[str] = os.getenv("QUANT_URL", "https://127.0.0.1:8000")
TIMEOUT: Final[int] = 5


def _wait(url: str, tries: int = 90, delay: float = 1.0) -> None:
    for _ in range(tries):
        try:
            if requests.get(f"{url}/readyz", timeout=TIMEOUT).ok:
                return
        except requests.RequestException:
            pass
        time.sleep(delay)
    print("timeout waiting for quantengine", file=sys.stderr)
    sys.exit(1)


def main() -> None:
    _wait(BASE)

    # Evaluate endpoint happy path
    eval_body = {
        "bank_id": "smoke_bank",
        "available_cash_usd": 50_000.0,
        "asof_ts": "2025-08-06T11:00:00Z",
        "policy": {
            "min_cash_bps": 100,
            "max_draw_bps": 5000,
            "settlement_calendar": [],
        },
    }
    r = requests.post(f"{BASE}/liquidity/evaluate", json=eval_body, timeout=TIMEOUT)
    r.raise_for_status()
    if not r.json().get("ok", False):
        print("liquidity evaluate failed", file=sys.stderr)
        sys.exit(1)

    # Publish dry-run
    pub_body = {
        "bank_id": "smoke_bank",
        "asof_ts": "2025-08-06T11:00:05Z",
        "available_cash_usd": 50_000.0,
        "reserved_buffer_usd": 5_000.0,
        "notes": "smoke-test",
    }
    r2 = requests.post(f"{BASE}/bridge/publish", json=pub_body, timeout=TIMEOUT)
    r2.raise_for_status()
    if not r2.json().get("ok", False):
        print("publish failed", file=sys.stderr)
        sys.exit(1)

    metrics = requests.get(f"{BASE}/metrics", timeout=TIMEOUT).text
    if "quant_publish_total" not in metrics:
        print("metrics missing", file=sys.stderr)
        sys.exit(1)

    print("LIQUIDITY SMOKE: OK")


if __name__ == "__main__":
    main()
