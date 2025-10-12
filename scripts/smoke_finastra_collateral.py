#!/usr/bin/env python3
from __future__ import annotations

"""
Runtime smoke for Finastra Collaterals metrics exposure and a lightweight API ping.

Usage:
  python scripts/smoke_finastra_collateral.py --url http://127.0.0.1:8050 --skip-api
  python scripts/smoke_finastra_collateral.py --url http://127.0.0.1:8050 \
      --metrics-out metrics.txt --junit-xml reports/results.xml --assert-breaker

Env:
  AGG_URL: fallback for --url
"""

import os
import sys
import argparse
import urllib.request
from xml.sax.saxutils import escape as _xml_escape

# Match metrics exported by bankersbank/finastra.py
REQUIRED_METRICS = [
    "finastra_api_calls_total",
    "finastra_api_latency_seconds_bucket",
    "finastra_breaker_state",
]


def http_get(url: str, timeout: int = 5):
    with urllib.request.urlopen(url, timeout=timeout) as r:  # nosec B310 (controlled URL in CI)
        return r.status, r.read().decode("utf-8", errors="replace")


def write_text(path: str, content: str) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write(content)


def _parse_breaker_value(metrics_body: str) -> float | None:
    # naive scan for last gauge sample value
    # e.g., finastra_breaker_state{client="collateral"} 0
    lines = [ln.strip() for ln in metrics_body.splitlines() if ln.startswith("finastra_breaker_state")]
    if not lines:
        return None
    last = lines[-1]
    try:
        return float(last.split()[-1])
    except Exception:
        return None


def _write_junit(path: str, name: str, ok: bool, message: str = "") -> None:
    classname = _xml_escape(name)
    msg = _xml_escape(message)
    body = (
        f"<?xml version='1.0' encoding='UTF-8'?>\n"
        f"<testsuite name='{classname}' tests='1' failures='{0 if ok else 1}'>\n"
        f"  <testcase classname='{classname}' name='{classname}'>\n"
        + ("" if ok else f"    <failure message='failed'>{msg}</failure>\n")
        + "  </testcase>\n</testsuite>\n"
    )
    write_text(path, body)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--url", default=os.getenv("AGG_URL", "http://127.0.0.1:8050"), help="Base URL for the running app")
    ap.add_argument("--skip-api", action="store_true", help="Skip the API ping, only check /metrics")
    ap.add_argument("--metrics-out", default=None, help="Write raw /metrics to this path for CI artifact")
    ap.add_argument("--junit-xml", default=None, help="Write a one-test JUnit XML result to this path")
    ap.add_argument("--assert-breaker", action="store_true", help="Fail if breaker gauge missing or invalid")
    args = ap.parse_args()

    # 1) Check /metrics
    base = args.url.rstrip("/")
    status, body = http_get(f"{base}/metrics", timeout=5)
    if status != 200:
        print(f"[FAIL] GET /metrics -> {status}", file=sys.stderr)
        if args.junit_xml:
            _write_junit(args.junit_xml, "metrics", False, f"GET /metrics -> {status}")
        return 1

    missing = [m for m in REQUIRED_METRICS if m not in body]
    if missing:
        print(f"[FAIL] Missing expected metrics in /metrics: {missing}", file=sys.stderr)
        if args.junit_xml:
            _write_junit(args.junit_xml, "metrics", False, f"missing: {', '.join(missing)}")
        return 2
    if args.metrics_out:
        write_text(args.metrics_out, body)

    # Optional breaker assertion
    if args.assert_breaker:
        val = _parse_breaker_value(body)
        if val is None or val not in (0, 1, 2):
            print(f"[FAIL] breaker gauge invalid: {val}", file=sys.stderr)
            if args.junit_xml:
                _write_junit(args.junit_xml, "metrics", False, f"breaker invalid: {val}")
            return 3

    # 2) Optional: ping list endpoint to confirm route is wired (feature remains B2B)
    if not args.skip_api:
        try:
            status, _ = http_get(f"{base}/finastra/b2b/collaterals?top=1&startingIndex=0", timeout=5)
            if status not in (200, 401, 403):  # 401/403 acceptable if auth required
                print(f"[WARN] collaterals list returned status={status}")
            else:
                print(f"[OK] collaterals list ping returned status={status}")
        except Exception as e:  # pragma: no cover
            print(f"[WARN] collaterals list ping failed: {e}")

    print("[PASS] finastra collateral smoke completed")
    if args.junit_xml:
        _write_junit(args.junit_xml, "metrics", True, "ok")
    return 0


if __name__ == "__main__":
    sys.exit(main())
