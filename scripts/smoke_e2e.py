import os
import sys
import time

import requests

BANK = os.getenv("BANK_CONNECTOR_URL", "http://localhost:8003")
AGGR = os.getenv("ASSET_AGGREGATOR_URL", "http://localhost:9000")


def wait_ready(url, tries=60, delay=2.0):
    for _ in range(tries):
        try:
            r = requests.get(url, timeout=2)
            if r.ok:
                return
        except Exception:
            pass
        time.sleep(delay)
    print(f"[SMOKE] Service not ready: {url}", file=sys.stderr)
    sys.exit(1)


def main():
    # wait for health endpoints
    wait_ready(f"{AGGR}/healthz")
    wait_ready(f"{BANK}/healthz")

    # create at least one snapshot to avoid 404 on empty DB
    r = requests.post(f"{AGGR}/snapshot", timeout=10, params={"bank_id": "O&L"})
    assert r.ok, r.text
    r = requests.get(f"{AGGR}/assets/summary", params={"bank_id": "O&L"}, timeout=5)
    assert r.status_code == 200 and isinstance(r.json(), dict), r.text

    # basic sweep order round-trip (Bank Connector)
    payload = {
        "order_id": "smoke-001",
        "amount": 100.0,
        "currency": "USD",
        "debtor": "ACME",
        "creditor": "LiquidityPool",
    }
    r = requests.post(f"{BANK}/sweep-order", json=payload, timeout=5)
    assert r.status_code == 200 and "id" in r.json(), r.text

    # metrics present
    m_bank = requests.get(f"{BANK}/metrics", timeout=5).text
    assert "sweep_latency_seconds" in m_bank, "expected bank_connector metric missing"
    m_aggr = requests.get(f"{AGGR}/metrics", timeout=5).text
    assert ("treas_ltv_ratio" in m_aggr) or (
        "snapshot_latency_seconds" in m_aggr
    ), "expected asset_aggregator metrics missing"

    print("SMOKE: OK")


if __name__ == "__main__":
    main()
