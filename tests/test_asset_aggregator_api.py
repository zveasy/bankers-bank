from __future__ import annotations

import sys

from fastapi.testclient import TestClient
import pytest
from sqlmodel import SQLModel


@pytest.fixture()
def client_api(monkeypatch: pytest.MonkeyPatch):
    db_url = "sqlite:///./test_asset_api.db"
    monkeypatch.setenv("ASSET_DB_URL", db_url)
    SQLModel.metadata.clear()
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
