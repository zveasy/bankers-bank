import pytest

try:
    from openapi_client import ApiClient, Configuration
    from openapi_client.api.default_api import DefaultApi  # ← change here
except Exception:  # pragma: no cover - SDK missing
    ApiClient = Configuration = DefaultApi = None


@pytest.mark.skipif(ApiClient is None, reason="openapi_client package missing")
def test_client_imports():
    cfg = Configuration(host="https://localhost:9999")
    api = DefaultApi(ApiClient(cfg))
    assert hasattr(api, "create_account")
