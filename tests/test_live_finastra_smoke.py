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


REQUIRED_ANY_CLIENT = (
    ("FINASTRA_CLIENT_ID", "FINASTRA_CLIENT_SECRET"),
    ("FINASTRA_B2B_CLIENT_ID", "FINASTRA_B2B_CLIENT_SECRET"),
    ("FINASTRA_B2C_CLIENT_ID", "FINASTRA_B2C_CLIENT_SECRET"),
)


@pytest.mark.asyncio
async def test_live_finastra_smoke(tmp_path: Path):
    # Skip if not opted-in or secrets missing
    if os.getenv("FINASTRA_SMOKE") != "1":
        pytest.skip("live Finastra smoke disabled (set FINASTRA_SMOKE=1 to enable)")
    # base url may be provided in different vars; require at least one
    base_url = (
        os.getenv("FINASTRA_BASE_URL")
        or os.getenv("FINASTRA_B2B_BASE_URL_ACCOUNTS")
        or os.getenv("FINASTRA_B2B_BASE_URL_ACCOUNTINFO")
        or os.getenv("FINASTRA_B2B_BASE_URL_BALANCES")
        or os.getenv("FINASTRA_B2B_BASE_URL_COLLATERALS")
    )
    if not base_url:
        pytest.skip("missing base URL (FINASTRA_BASE_URL or FINASTRA_B2B_BASE_URL_*)")

    # require one of the client-id/secret pairs to be present
    has_pair = any(os.getenv(a) and os.getenv(b) for a, b in REQUIRED_ANY_CLIENT)
    if not has_pair:
        pytest.skip("missing client credentials (B2B/B2C or classic)")

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
