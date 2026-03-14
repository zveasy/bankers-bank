from __future__ import annotations

import asyncio
import sys
import json
import httpx

from fastapi.testclient import TestClient
import pytest
from sqlmodel import SQLModel


@pytest.fixture()
def client_api(monkeypatch: pytest.MonkeyPatch):
    db_url = "sqlite:///./test_asset_api.db"
    monkeypatch.setenv("ASSET_DB_URL", db_url)
    sys.modules.pop("asset_aggregator.db", None)
    sys.modules.pop("asset_aggregator.api", None)
    import asset_aggregator.api as api
    monkeypatch.setattr(api, "reconcile_snapshot", lambda *args, **kwargs: None)
    return TestClient(api.app), api


def test_snapshot_accepts_explicit_bank_id(client_api, monkeypatch: pytest.MonkeyPatch):
    client, api = client_api
    captured: dict[str, str | None] = {}

    def fake_run_snapshot_once(bank_id: str | None):
        captured["bank_id"] = bank_id
        return ("ok", 0.1)

    monkeypatch.setattr(api, "run_snapshot_once", fake_run_snapshot_once)
    resp = client.post(
        "/snapshot", params={"bank_id": "B1"}, headers={"Authorization": "Bearer testtoken"}
    )
    assert resp.status_code == 200, resp.text
    assert captured["bank_id"] == "B1"


def test_snapshot_accepts_missing_bank_id(client_api, monkeypatch: pytest.MonkeyPatch):
    client, api = client_api
    captured: dict[str, str | None] = {}

    def fake_run_snapshot_once(bank_id: str | None):
        captured["bank_id"] = bank_id
        return ("ok", 0.1)

    monkeypatch.setattr(api, "run_snapshot_once", fake_run_snapshot_once)
    resp = client.post("/snapshot", headers={"Authorization": "Bearer testtoken"})
    assert resp.status_code == 200, resp.text
    assert captured["bank_id"] == "O&L"


def test_readyz_is_unauthenticated(client_api, monkeypatch: pytest.MonkeyPatch):
    client, api = client_api

    class _Sock:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return None

    monkeypatch.setattr(api.socket, "create_connection", lambda *_args, **_kwargs: _Sock())
    resp = client.get("/readyz")
    assert resp.status_code == 200, resp.text
    assert resp.json()["ok"] is True


def test_b2b_collaterals_supports_tenant_override(client_api, monkeypatch: pytest.MonkeyPatch):
    client, api = client_api
    monkeypatch.setenv("FEATURE_FINASTRA_COLLATERALS", "1")
    captured: dict[str, str | None] = {"tenant": None}

    class _DummyClient:
        tenant = "tenant-a"

        def list_collaterals(self, startingIndex: int, pageSize: int):  # noqa: N803
            return {"items": [{"id": "c-1"}], "startingIndex": startingIndex, "pageSize": pageSize}

    def _fake_fin_client(tenant_override: str | None = None):
        captured["tenant"] = tenant_override
        return _DummyClient()

    monkeypatch.setattr(api, "_fin_client", _fake_fin_client)
    resp = client.get(
        "/finastra/b2b/collaterals?tenant=tenant-a&top=5&startingIndex=0",
        headers={"Authorization": "Bearer testtoken"},
    )
    assert resp.status_code == 200, resp.text
    assert captured["tenant"] == "tenant-a"
    assert resp.json()["items"][0]["id"] == "c-1"


def test_b2c_accounts_feature_disabled_by_default(client_api):
    client, _ = client_api
    resp = client.get("/finastra/b2c/accounts", headers={"Authorization": "Bearer testtoken"})
    assert resp.status_code == 404


def test_b2c_accounts_fetches_live_data(client_api, monkeypatch: pytest.MonkeyPatch):
    client, api = client_api
    monkeypatch.setenv("FEATURE_FINASTRA_B2C", "1")

    captured_cfg: dict[str, str] = {}

    class _Acc:
        def __init__(self, external_id: str, raw: dict):
            self.external_id = external_id
            self.raw = raw

    class _FakeAccountsClient:
        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return None

        async def list_accounts(self, account_context: str, *, limit: int = 50):
            yield [_Acc("acc-1", {"id": f"{account_context}-1", "limit": limit})]

    def _fake_build_accounts_client(cfg):
        captured_cfg["tenant"] = cfg.tenant
        return _FakeAccountsClient()

    monkeypatch.setattr(api, "_build_accounts_client", _fake_build_accounts_client)
    resp = client.get(
        "/finastra/b2c/accounts?contexts=CTX-1&contexts=CTX-2&limit=10&tenant=tenant-a",
        headers={"Authorization": "Bearer testtoken"},
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["meta"]["tenant"] == "tenant-a"
    assert body["meta"]["contexts"] == ["CTX-1", "CTX-2"]
    assert len(body["items"]) == 2
    assert captured_cfg["tenant"] == "tenant-a"


def test_b2c_balances_infers_account_ids_from_accounts(client_api, monkeypatch: pytest.MonkeyPatch):
    client, api = client_api
    monkeypatch.setenv("FEATURE_FINASTRA_B2C", "1")

    class _Acc:
        def __init__(self, external_id: str):
            self.external_id = external_id
            self.raw = {"id": external_id}

    captured_ids: dict[str, list[str]] = {"ids": []}

    class _FakeAccountsClient:
        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return None

        async def list_accounts(self, account_context: str, *, limit: int = 50):
            yield [_Acc("acc-1"), _Acc("acc-2")]

    class _FakeBalancesClient:
        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return None

        async def list_all_balances(self, account_ids: list[str]):
            captured_ids["ids"] = account_ids
            yield [
                {"accountId": account_ids[0], "currentAmount": 100, "currency": "USD"},
                {"accountId": account_ids[1], "currentAmount": 200, "currency": "USD"},
            ]

    monkeypatch.setattr(api, "_build_accounts_client", lambda cfg: _FakeAccountsClient())
    monkeypatch.setattr(api, "_build_balances_client", lambda cfg: _FakeBalancesClient())

    resp = client.get(
        "/finastra/b2c/balances?tenant=tenant-b&contexts=CTX-1",
        headers={"Authorization": "Bearer testtoken"},
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert captured_ids["ids"] == ["acc-1", "acc-2"]
    assert body["meta"]["tenant"] == "tenant-b"
    assert len(body["items"]) == 2


def test_resolve_tenant_oauth_config_prefers_json_map(client_api, monkeypatch: pytest.MonkeyPatch):
    _, api = client_api
    monkeypatch.setenv(
        "FINASTRA_TENANT_CONFIG_JSON",
        json.dumps(
            {
                "tenant-a": {
                    "base_url": "https://tenant-a.example",
                    "client_id": "cid-a",
                    "client_secret": "sec-a",
                    "scope": "openid accounts",
                    "token_url": "https://tenant-a.example/token",
                }
            }
        ),
    )

    cfg = api._resolve_tenant_oauth_config(
        "tenant-a",
        client_id_vars=("FINASTRA_B2C_CLIENT_ID", "FINASTRA_CLIENT_ID"),
        client_secret_vars=("FINASTRA_B2C_CLIENT_SECRET", "FINASTRA_CLIENT_SECRET"),
    )
    assert cfg.tenant == "tenant-a"
    assert cfg.base_url == "https://tenant-a.example"
    assert cfg.client_id == "cid-a"
    assert cfg.client_secret == "sec-a"
    assert cfg.scope == "openid accounts"
    assert cfg.token_url == "https://tenant-a.example/token"


def test_b2c_accounts_partial_context_failure_returns_success(client_api, monkeypatch: pytest.MonkeyPatch):
    client, api = client_api
    monkeypatch.setenv("FEATURE_FINASTRA_B2C", "1")

    class _Acc:
        def __init__(self, external_id: str, raw: dict):
            self.external_id = external_id
            self.raw = raw

    class _FakeAccountsClient:
        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return None

        async def list_accounts(self, account_context: str, *, limit: int = 50):
            if account_context == "BAD":
                req = httpx.Request("GET", "https://example/accounts")
                resp = httpx.Response(404, request=req, text="not found")
                raise httpx.HTTPStatusError("not found", request=req, response=resp)
            yield [_Acc("acc-ok", {"id": "acc-ok", "ctx": account_context})]

    monkeypatch.setattr(api, "_build_accounts_client", lambda cfg: _FakeAccountsClient())
    resp = client.get(
        "/finastra/b2c/accounts?contexts=BAD&contexts=GOOD",
        headers={"Authorization": "Bearer testtoken"},
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert len(body["items"]) == 1
    assert body["meta"]["context_errors"][0]["context"] == "BAD"
    metrics = client.get("/metrics")
    assert metrics.status_code == 200
    assert "finastra_b2c_context_errors_total" in metrics.text


def test_b2c_accounts_all_contexts_fail_returns_error(client_api, monkeypatch: pytest.MonkeyPatch):
    client, api = client_api
    monkeypatch.setenv("FEATURE_FINASTRA_B2C", "1")

    class _FakeAccountsClient:
        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return None

        async def list_accounts(self, account_context: str, *, limit: int = 50):
            req = httpx.Request("GET", "https://example/accounts")
            resp = httpx.Response(404, request=req, text=f"missing:{account_context}")
            raise httpx.HTTPStatusError("not found", request=req, response=resp)
            yield  # pragma: no cover

    monkeypatch.setattr(api, "_build_accounts_client", lambda cfg: _FakeAccountsClient())
    resp = client.get(
        "/finastra/b2c/accounts?contexts=BAD1&contexts=BAD2",
        headers={"Authorization": "Bearer testtoken"},
    )
    assert resp.status_code == 404
    detail = resp.json()["detail"]
    assert detail["error"] == "all_contexts_failed"


def test_b2c_balances_all_contexts_fail_returns_error(client_api, monkeypatch: pytest.MonkeyPatch):
    client, api = client_api
    monkeypatch.setenv("FEATURE_FINASTRA_B2C", "1")

    class _FakeAccountsClient:
        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return None

        async def list_accounts(self, account_context: str, *, limit: int = 50):
            req = httpx.Request("GET", "https://example/accounts")
            resp = httpx.Response(404, request=req, text=f"missing:{account_context}")
            raise httpx.HTTPStatusError("not found", request=req, response=resp)
            yield  # pragma: no cover

    monkeypatch.setattr(api, "_build_accounts_client", lambda cfg: _FakeAccountsClient())
    resp = client.get(
        "/finastra/b2c/balances?contexts=BAD1&contexts=BAD2",
        headers={"Authorization": "Bearer testtoken"},
    )
    assert resp.status_code == 404
    detail = resp.json()["detail"]
    assert detail["error"] == "all_contexts_failed"


def test_async_token_adapter_refresh_invalidates_provider_cache(client_api):
    _, api = client_api

    class _Provider:
        def __init__(self):
            self._access_token = "cached-token"
            self._expires_at = 9999999999.0
            self.calls = 0
            self.seen_invalidated = False

        def fetch(self):
            self.calls += 1
            self.seen_invalidated = self._access_token is None and self._expires_at == 0.0
            self._access_token = f"token-{self.calls}"
            return self._access_token

    provider = _Provider()
    adapter = api._AsyncTokenProviderAdapter(provider)
    token = asyncio.run(adapter.refresh())
    assert token == "token-1"
    assert provider.calls == 1
    assert provider.seen_invalidated is True
