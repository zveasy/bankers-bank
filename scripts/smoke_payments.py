"""
In-memory smoke test for the bank_connector Rails path.
No outbound network calls; httpx.AsyncClient is patched to MockTransport.
Prints 'PAYMENTS SMOKE: OK' on success and exits 0.
"""

import os
import sys

import httpx
from fastapi.testclient import TestClient

import bank_connector.main as bc


def _patch_httpx_success():
    async def handler(request: httpx.Request) -> httpx.Response:  # noqa: D401
        return httpx.Response(200)

    class Patched(httpx.AsyncClient):
        def __init__(self, *args, **kwargs):
            kwargs.setdefault("transport", httpx.MockTransport(handler))
            super().__init__(*args, **kwargs)

    # Patch global and local module refs
    httpx.AsyncClient = Patched  # type: ignore[assignment]
    bc.httpx.AsyncClient = Patched  # type: ignore[attr-defined]


def main() -> int:
    os.environ.setdefault("BANK_RAILS_ENABLED", "1")
    os.environ.setdefault("BANK_RAILS_URL", "http://rails.test")

    _patch_httpx_success()

    client = TestClient(bc.app)

    payload = {
        "order_id": "SMOKE-1",
        "amount": 10.0,
        "currency": "USD",
        "debtor": "Alice",
        "creditor": "Bob",
    }

    resp = client.post("/sweep-order", json=payload)
    if resp.status_code != 200:
        print(
            f"SMOKE ERR: /sweep-order {resp.status_code} – {resp.text}", file=sys.stderr
        )
        return 1

    metrics = client.get("/metrics").text
    if "rails_post_total" not in metrics or 'result="ok"' not in metrics:
        print("SMOKE WARN: rails_post_total metric not observed", file=sys.stderr)

    print("PAYMENTS SMOKE: OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
