from fastapi.testclient import TestClient

from quantengine.main import app


def test_readyz_ok():
    client = TestClient(app)
    r = client.get("/readyz", headers={"Authorization": "Bearer testtoken"})
    assert r.status_code == 200
    assert r.json().get("ok") is True


def test_readyz_unauthorized():
    client = TestClient(app)
    r = client.get("/readyz")
    assert r.status_code == 401
