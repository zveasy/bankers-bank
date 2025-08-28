"""Conditional live smoke test against Finastra sandbox.

This runs only when the required secrets are present *and* the environment variable
`FINASTRA_SMOKE` is set to "1". Otherwise the test is skipped.

It performs a single Accounts & Balances call to verify auth/token flow and basic
API reachability. The test records the `ff-trace-id` header (if provided) into
`fin_trace_id.txt` so that the CI workflow can publish it as an artifact for
later debugging.
"""
from __future__ import annotations

import asyncio
import os
from pathlib import Path

import pytest

from integrations.finastra.accounts_client import AccountsClient
from integrations.finastra.balances_client import BalancesClient


REQUIRED_VARS = [
    "FINASTRA_BASE_URL",
    "FINASTRA_CLIENT_ID",
    "FINASTRA_CLIENT_SECRET",
    "FINASTRA_TENANT_ID",
]


@pytest.mark.asyncio
async def test_live_finastra_smoke(tmp_path: Path):
    # Skip if not opted-in or secrets missing
    if os.getenv("FINASTRA_SMOKE") != "1":
        pytest.skip("live Finastra smoke disabled (set FINASTRA_SMOKE=1 to enable)")
    if missing := [v for v in REQUIRED_VARS if not os.getenv(v)]:
        pytest.skip("missing env vars: " + ", ".join(missing))

    acct_client = AccountsClient()
    bal_client = BalancesClient()

    # We don't know tenant contexts ahead, so just try first page default context
    async with asyncio.TaskGroup() as tg:  # Python 3.11+
        acct_task = tg.create_task(acct_client.list_accounts_page(context="MT103", page_size=1))
        bal_task = tg.create_task(bal_client.list_balances_page(page_size=1))

    accounts = acct_task.result()
    balances = bal_task.result()

    assert accounts, "no accounts returned"
    assert balances, "no balances returned"

    # Record trace-id if present (helpful for dbg)
    trace_id = (
        acct_client.last_response.headers.get("ff-trace-id")  # type: ignore[attr-defined]
        if getattr(acct_client, "last_response", None) else None
    )
    if trace_id:
        (Path.cwd() / "fin_trace_id.txt").write_text(trace_id)
