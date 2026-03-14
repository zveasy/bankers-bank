from __future__ import annotations

import os
import pytest
from fastapi.testclient import TestClient

from asset_aggregator.api import app as aggregator_app

pytestmark = [pytest.mark.finastra_live]

REQUIRED = (
    "FINASTRA_B2C_CLIENT_ID",
    "FINASTRA_B2C_CLIENT_SECRET",
    "FINASTRA_B2C_BASE_URL",
    "FINASTRA_TENANT",
)


def _have_env() -> bool:
    return all(os.getenv(k) for k in REQUIRED)


def _require_200() -> bool:
    return os.getenv("FINASTRA_B2C_REQUIRE_200", "0").lower() in ("1", "true", "yes")


def _auth_headers() -> dict[str, str]:
    # tests/conftest.py installs API_TOKENS.tester=testtoken
    return {"Authorization": "Bearer testtoken"}


@pytest.mark.skipif(not _have_env(), reason="Missing Finastra B2C live env")
def test_live_b2c_accounts_smoke(monkeypatch):
    monkeypatch.setenv("FEATURE_FINASTRA_B2C", "1")
    ctx = os.getenv("FINASTRA_B2C_SMOKE_CONTEXT", "MT103")
    client = TestClient(aggregator_app)
    r = client.get(
        f"/finastra/b2c/accounts?contexts={ctx}&limit=1",
        headers=_auth_headers(),
    )
    if _require_200():
        assert r.status_code == 200, r.text
    else:
        assert r.status_code in (200, 404), r.text
    if r.status_code == 200:
        body = r.json()
        assert "items" in body
        assert isinstance(body["items"], list)


@pytest.mark.skipif(not _have_env(), reason="Missing Finastra B2C live env")
def test_live_b2c_balances_smoke(monkeypatch):
    monkeypatch.setenv("FEATURE_FINASTRA_B2C", "1")
    ctx = os.getenv("FINASTRA_B2C_SMOKE_CONTEXT", "MT103")
    client = TestClient(aggregator_app)
    r = client.get(
        f"/finastra/b2c/balances?contexts={ctx}&limit=1",
        headers=_auth_headers(),
    )
    if _require_200():
        assert r.status_code == 200, r.text
    else:
        assert r.status_code in (200, 404), r.text
    if r.status_code == 200:
        body = r.json()
        assert "items" in body
        assert isinstance(body["items"], list)


@pytest.mark.skipif(
    not (_have_env() and os.getenv("FINASTRA_B2C_TENANT_ALIAS")),
    reason="Missing B2C live env or FINASTRA_B2C_TENANT_ALIAS",
)
def test_live_b2c_accounts_tenant_override_smoke(monkeypatch):
    monkeypatch.setenv("FEATURE_FINASTRA_B2C", "1")
    ctx = os.getenv("FINASTRA_B2C_SMOKE_CONTEXT", "MT103")
    alias = os.environ["FINASTRA_B2C_TENANT_ALIAS"]
    client = TestClient(aggregator_app)
    r = client.get(
        f"/finastra/b2c/accounts?tenant={alias}&contexts={ctx}&limit=1",
        headers=_auth_headers(),
    )
    if _require_200():
        assert r.status_code == 200, r.text
    else:
        assert r.status_code in (200, 404), r.text
