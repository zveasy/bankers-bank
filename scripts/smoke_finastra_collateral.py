#!/usr/bin/env python3
from __future__ import annotations

"""
Runtime smoke for Finastra Collaterals metrics exposure and a lightweight API ping.

Usage:
  python scripts/smoke_finastra_collateral.py --url http://127.0.0.1:8050 --skip-api
  python scripts/smoke_finastra_collateral.py --url http://127.0.0.1:8050

Env:
  AGG_URL: fallback for --url
"""

import os
import sys
import argparse
import urllib.request

# Match metrics exported by bankersbank/finastra.py
REQUIRED_METRICS = [
    "finastra_api_calls_total",
    "finastra_api_latency_seconds",
]


def http_get(url: str, timeout: int = 5):
    with urllib.request.urlopen(url, timeout=timeout) as r:  # nosec B310 (controlled URL in CI)
        return r.status, r.read().decode("utf-8", errors="replace")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--url", default=os.getenv("AGG_URL", "http://127.0.0.1:8050"), help="Base URL for the running app")
    ap.add_argument("--skip-api", action="store_true", help="Skip the API ping, only check /metrics")
    args = ap.parse_args()

    base = args.url.rstrip("/")

    # 1) Check /metrics
    status, body = http_get(f"{base}/metrics", timeout=5)
    if status != 200:
        print(f"[FAIL] GET /metrics -> {status}", file=sys.stderr)
        return 1

    missing = [m for m in REQUIRED_METRICS if m not in body]
    if missing:
        print(f"[FAIL] Missing expected metrics in /metrics: {missing}", file=sys.stderr)
        return 2
    print("[OK] /metrics exposes required Finastra metrics")

    # 2) Optional: ping list endpoint to confirm route is wired (feature remains B2B)
    if not args.skip_api:
        # NOTE: your app's auth may guard this route; if so, adjust headers accordingly
        try:
            status, _ = http_get(f"{base}/finastra/b2b/collaterals?top=1&startingIndex=0", timeout=5)
            if status not in (200, 401, 403):  # 401/403 acceptable if auth required
                print(f"[WARN] collaterals list returned status={status}")
            else:
                print(f"[OK] collaterals list ping returned status={status}")
        except Exception as e:  # pragma: no cover
            print(f"[WARN] collaterals list ping failed: {e}")

    print("[PASS] finastra collateral smoke completed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
