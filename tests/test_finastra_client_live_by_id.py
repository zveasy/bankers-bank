import os
import pytest
import requests
from bankersbank.finastra import ClientCredentialsTokenProvider, FinastraAPIClient

pytestmark = [pytest.mark.finastra_live]

REQUIRED = (
    "FINASTRA_B2B_CLIENT_ID",
    "FINASTRA_B2B_CLIENT_SECRET",
    "FINASTRA_B2B_BASE_URL_COLLATERALS",
    "FINASTRA_TENANT",
    "TEST_COLLATERAL_ID_PRIMARY",
)

def _have_env():
    return all(os.getenv(k) for k in REQUIRED)


@pytest.mark.skipif(not _have_env(), reason="Missing Finastra live env or test collateral id")
def test_live_get_collateral_smoke():
    base_url_product = os.environ["FINASTRA_B2B_BASE_URL_COLLATERALS"].rstrip("/")
    tenant = os.environ["FINASTRA_TENANT"]
    cid = os.environ["TEST_COLLATERAL_ID_PRIMARY"]

    # Determine auth host (scheme+netloc) to avoid putting product path before /login
    auth_url = os.getenv("FINASTRA_AUTH_URL")
    if auth_url:
        try:
            from urllib.parse import urlparse
            p = urlparse(auth_url)
            auth_base = f"{p.scheme}://{p.netloc}"
        except Exception:
            auth_base = "https://api.fusionfabric.cloud"
    else:
        # Derive from product base by stripping path
        try:
            from urllib.parse import urlparse
            p = urlparse(base_url_product)
            auth_base = f"{p.scheme}://{p.netloc}"
        except Exception:
            auth_base = "https://api.fusionfabric.cloud"

    scope = os.getenv("FINASTRA_SCOPE", "openid")
    token_provider = ClientCredentialsTokenProvider(
        base_url=auth_base,
        tenant=tenant,
        client_id=os.environ["FINASTRA_B2B_CLIENT_ID"],
        client_secret=os.environ["FINASTRA_B2B_CLIENT_SECRET"],
        scope=scope,
    )
    client = FinastraAPIClient(
        base_url=base_url_product,
        tenant=tenant,
        product="total-lending/collaterals/b2b/v2",
        token_provider=token_provider,
    )

    # 404 is acceptable in sandbox by default; enable strict mode with FINASTRA_REQUIRE_200=1
    require_200 = os.getenv("FINASTRA_REQUIRE_200", "0").lower() in ("1", "true", "yes")
    try:
        r = client.request("GET", f"/collaterals/{cid}")
        if require_200:
            assert r.status_code == 200
        else:
            assert r.status_code in (200, 404)
    except requests.HTTPError as e:
        if require_200:
            import pytest as _pytest
            _pytest.fail(f"Expected 200 in strict mode, got {getattr(e.response, 'status_code', 'ERR')}")
        else:
            assert e.response is not None and e.response.status_code == 404
