"""Quick smoke test for credit_facility running in Docker.

Usage (PowerShell):

```powershell
$env:CREDIT_URL="http://127.0.0.1:8050"
poetry run python scripts/smoke_credit.py
```
"""
from __future__ import annotations

import os
import sys
import time
from typing import Final

import requests

BASE: Final[str] = os.getenv("CREDIT_URL", "http://127.0.0.1:8050")
TIMEOUT: Final[int] = 5


def _wait_for_service(url: str, tries: int = 90, delay: float = 1.0) -> None:
    for _ in range(tries):
        try:
            if requests.get(f"{url}/healthz", timeout=TIMEOUT).ok:
                return
        except requests.RequestException:
            pass
        time.sleep(delay)
    print("timeout waiting for credit_facility", file=sys.stderr)
    sys.exit(1)


def main() -> None:
    _wait_for_service(BASE)

    headers = {"Idempotency-Key": "idem-smoke-1", "Content-Type": "application/json"}
    draw_body = {"bank_id": "b1", "amount": 100.0, "currency": "USD"}

    r1 = requests.post(f"{BASE}/api/credit/v1/draw", json=draw_body, headers=headers, timeout=TIMEOUT)
    r1.raise_for_status()

    # idempotent replay should not fail (200 or 201)
    r2 = requests.post(f"{BASE}/api/credit/v1/draw", json=draw_body, headers=headers, timeout=TIMEOUT)
    if r2.status_code not in (200, 201):
        print(f"Unexpected status for idempotent replay: {r2.status_code}", file=sys.stderr)
        sys.exit(1)

    status = requests.get(f"{BASE}/api/credit/v1/b1/status", timeout=TIMEOUT).json()
    assert "available" in status and "outstanding" in status, "Status response missing keys"

    metrics_text = requests.get(f"{BASE}/metrics", timeout=TIMEOUT).text
    if "credit_actions_total" not in metrics_text or "credit_provider_latency_seconds_bucket" not in metrics_text:
        print("Expected metrics not found", file=sys.stderr)
        sys.exit(1)

    print("CREDIT SMOKE: OK")


if __name__ == "__main__":
    main()
