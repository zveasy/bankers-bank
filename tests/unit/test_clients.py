from openapi_client import ApiClient, Configuration
from openapi_client.api.default_api import DefaultApi   # ← change here

def test_client_imports():
    cfg = Configuration(host="http://localhost:9999")
    api = DefaultApi(ApiClient(cfg))
    assert hasattr(api, "create_account")
