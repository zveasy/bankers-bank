import pytest

try:
    import yaml
except ImportError:  # pragma: no cover - environment lacks PyYAML
    yaml = None

@pytest.mark.skipif(yaml is None, reason="PyYAML not installed")
def test_accounts_endpoint_exists():
    with open("api/openapi.yaml") as f:
        spec = yaml.safe_load(f)

    assert "/v1/accounts" in spec.get("paths", {})
    assert "post" in spec["paths"]["/v1/accounts"]

@pytest.mark.skipif(yaml is None, reason="PyYAML not installed")
def test_new_account_schema():
    with open("api/openapi.yaml") as f:
        spec = yaml.safe_load(f)

    new_account = spec["components"]["schemas"]["NewAccount"]
    assert new_account["type"] == "object"
    assert set(new_account["required"]) == {"legal_name", "type", "currency"}
