# bankersbank/finastra.py
import os
import time
import random
import uuid
import logging
from dataclasses import dataclass
from typing import Any, Dict, Optional

import requests
from requests.adapters import HTTPAdapter

try:
    # urllib3 moved between major versions; both imports are handled
    from urllib3.util.retry import Retry  # type: ignore
except Exception:  # pragma: no cover
    from requests.packages.urllib3.util.retry import Retry  # type: ignore

# --- Prometheus (optional) ----------------------------------------------------
# If prometheus_client is not installed in all envs/CI, fall back to no-op.
try:  # pragma: no cover
    from prometheus_client import Counter, Histogram
except Exception:  # pragma: no cover
    class _Noop:
        def labels(self, *_, **__): return self
        def inc(self, *_: Any, **__: Any) -> None: ...
        def observe(self, *_: Any, **__: Any) -> None: ...
    def Counter(*_args, **_kwargs): return _Noop()
    def Histogram(*_args, **_kwargs): return _Noop()

# --- Prometheus metrics -----------------
_payments_initiate_total = Counter("payments_initiate_total", "Payments initiate calls", labelnames=["result"])
_payments_status_total = Counter("payments_status_total", "Payments status calls", labelnames=["result"])
_loans_read_total = Counter("loans_read_total", "Loans read calls", labelnames=["endpoint", "result"])
_collateral_read_total = Counter("collateral_read_total", "Collateral read calls", labelnames=["endpoint", "result"])
_latency_hist = Histogram("finastra_pay_loans_latency_seconds", "Latency for payments & loans", buckets=(0.1,0.3,0.5,1,2,5,10))
_non_2xx_total = Counter("finastra_non_2xx_total", "Non-2xx responses", labelnames=["status_bucket"])

__all__ = [
    "ClientCredentialsTokenProvider",
    "FinastraAPIClient",
    "fetch_token",
]

_log = logging.getLogger(__name__)
if not logging.getLogger().hasHandlers():
    logging.basicConfig(level=os.getenv("LOG_LEVEL", "INFO").upper())

# --- Env / Defaults -----------------------------------------------------------
FINASTRA_BASE_URL = os.getenv("FINASTRA_BASE_URL", "https://api.fusionfabric.cloud").rstrip("/")
FINASTRA_TENANT = os.getenv("FINASTRA_TENANT", "sandbox")

# Product roots (env-overridable)
FINASTRA_PRODUCT_COLLATERAL = os.getenv(
    "FINASTRA_PRODUCT_COLLATERAL", "total-lending/collaterals/b2b/v2"
).strip("/")

FINASTRA_PRODUCT_ACCOUNTS = os.getenv(
    "FINASTRA_PRODUCT_ACCOUNTS", "account-information/v2"
).strip("/")

FINASTRA_PRODUCT_PAYMENTS = os.getenv(
    "FINASTRA_PRODUCT_PAYMENTS", "payments/b2b/v1"
).strip("/")

FINASTRA_PRODUCT_LOANS = os.getenv(
    "FINASTRA_PRODUCT_LOANS", "total-lending/loans/b2b/v1"
).strip("/")

# Local/mock flag used in this repo
def _use_mock() -> bool:
    return os.getenv("USE_MOCK_BALANCES", "false").lower() in ("1", "true", "yes")

# Token endpoint (OIDC)
def _token_url(base_url: str, tenant: str) -> str:
    return f"{base_url.rstrip('/')}/login/v1/{tenant}/oidc/token"

# --- HTTP session with retries ------------------------------------------------
def _build_session() -> requests.Session:
    s = requests.Session()
    retry = Retry(
        total=3,
        read=3,
        connect=3,
        backoff_factor=0.5,
        status_forcelist=(429, 500, 502, 503, 504),
        allowed_methods=frozenset(["GET", "HEAD", "OPTIONS"]),
        raise_on_status=False,
    )
    s.mount("https://", HTTPAdapter(max_retries=retry))
    s.mount("http://", HTTPAdapter(max_retries=retry))
    return s

# --- Token Provider -----------------------------------------------------------
@dataclass
class ClientCredentialsTokenProvider:
    """
    Minimal client-credentials token cache/refresh.

    - Caches the token and refreshes a bit early (dynamic skew).
    - Skew = max(1s, min(60s, expires_in // 3)) so very short-lived tokens
      (like 2s in tests) are not refreshed immediately.
    """

    def __init__(
        self,
        client_id: str = None,
        client_secret: str = None,
        scope: str = "accounts",
        token_url: Optional[str] = None,
        verify: bool | str = True,
        session: Optional[requests.Session] = None,
        # Back-compat (if base_url + tenant are provided instead of token_url)
        base_url: Optional[str] = None,
        tenant: Optional[str] = None,
    ):
        # Prefer explicit token_url
        if token_url:
            self.token_url = token_url
        elif base_url and tenant:
            self.token_url = f"{base_url.rstrip('/')}/login/v1/{tenant}/oidc/token"
        else:
            # fall back to global TOKEN_URL constant if defined
            self.token_url = globals().get("TOKEN_URL")

        if not self.token_url:
            raise ValueError("No token_url provided and TOKEN_URL is not defined")

        self.client_id = client_id
        self.client_secret = client_secret
        self.scope = scope
        self.verify = verify
        self.session = session or _build_session()

        self._access_token: Optional[str] = None
        self._expires_at: float = 0.0           # epoch seconds
        self._refresh_skew: int = 10            # default before first fetch

    def _expired(self) -> bool:
        # refresh a bit before actual expiry using dynamic skew
        return (not self._access_token) or (time.time() >= self._expires_at - self._refresh_skew)

    def _fetch_impl(self) -> str:
        """
        Internal: fetch a fresh token from the OIDC endpoint.
        Uses requests.post (not the session) so tests can monkeypatch fin.requests.post.
        """
        headers = {"Content-Type": "application/x-www-form-urlencoded"}
        data = {
            "grant_type": "client_credentials",
            "client_id": self.client_id,
            "client_secret": self.client_secret,
            "scope": self.scope,
        }
        # IMPORTANT: use requests.post here (tests monkeypatch fin.requests.post)
        resp = requests.post(self.token_url, headers=headers, data=data, timeout=30, verify=self.verify)
        resp.raise_for_status()
        body = resp.json()

        token = body.get("access_token", "")
        if not token:
            raise RuntimeError("Token response missing 'access_token'")

        expires_in = int(body.get("expires_in", 300))
        now = time.time()
        # refresh skew: refresh a bit before expiry; bounded for tiny/huge TTLs
        skew = max(1, min(60, expires_in // 3))
        self._access_token = token
        self._expires_at = now + expires_in
        self._refresh_skew = skew
        return token

    # Public API expected by tests
    def fetch(self) -> str:
        if self._expired():
            return self._fetch_impl()
        return self._access_token or ""

    # Back-compat alias some code might still call
    def get_token(self) -> str:
        return self.fetch()


# Convenience (back-compat) helper
def fetch_token(
    client_id: str,
    client_secret: str,
    scope: str = "accounts",
    base_url: str = FINASTRA_BASE_URL,
    tenant: str = FINASTRA_TENANT,
    verify: bool | str = True,
) -> str:
    return ClientCredentialsTokenProvider(
        base_url=base_url,
        tenant=tenant,
        client_id=client_id,
        client_secret=client_secret,
        scope=scope,
        verify=verify,
    ).fetch()

# --- Client -------------------------------------------------------------------
class FinastraAPIClient:
    """
    Minimal client for Finastra APIs (Accounts/Collaterals + Payments/Loans scaffolding).
    - Automatic bearer from ClientCredentialsTokenProvider (or pre-supplied token string).
    - Retries (GET) and sane timeouts.
    - JSON helpers.
    """

    def __init__(
        self,
        base_url: str = FINASTRA_BASE_URL,
        tenant: str = FINASTRA_TENANT,
        product: str = FINASTRA_PRODUCT_COLLATERAL,
        token_provider: ClientCredentialsTokenProvider | None = None,
        token: str | None = None,
        # legacy alias for callers that pass token via positional arg
        token_or_provider: str | None = None,
        verify: bool | str = True,
        timeout: int = 30,
        session: Optional[requests.Session] = None,
        mock_base_url: str = "http://127.0.0.1:8000",
    ):
        # accept legacy alias
        if token_or_provider and not token:
            token = token_or_provider

        self.base_url = base_url.rstrip("/")
        self.tenant = tenant
        self.product = product.strip("/")
        self.verify = verify
        self.timeout = timeout
        self.session = session or _build_session()
        self.mock_base_url = mock_base_url.rstrip("/")

        if token_provider is None and token is None:
            raise ValueError("Provide either token_provider or token.")
        self._provider = token_provider
        self._token = token

    # --- headers/url builders -------------------------------------------------
    def _bearer(self) -> str:
        if self._provider is not None:
            return self._provider.fetch()
        return self._token or ""

    def _headers(self, extra: Optional[Dict[str, str]] = None) -> Dict[str, str]:
        h = {
            "Authorization": f"Bearer {self._bearer()}",
            "Accept": "application/json",
            "Content-Type": "application/json",
            "X-Request-ID": str(uuid.uuid4()),  # default request correlation
        }
        if extra:
            h.update(extra)
        return h

    def _root(self, product: Optional[str] = None) -> str:
        if _use_mock():
            # In tests, base_url may be "http://testserver" (FastAPI TestClient)
            # Prefer an explicitly provided base_url in mock mode; fallback to default mock_base_url.
            base = (self.base_url or self.mock_base_url).rstrip("/")
            return base
        prod = (product or self.product).strip("/")
        return f"{self.base_url}/{prod}"

    def _url(self, path: str, product: Optional[str] = None) -> str:
        path = path if path.startswith("/") else f"/{path}"
        return f"{self._root(product)}{path}"

    # --- core request helpers -------------------------------------------------
    def request(self, method: str, path: str, **kwargs) -> requests.Response:
        url = self._url(path, kwargs.pop("product", None))
        headers = self._headers(kwargs.pop("headers", None))
        timeout = kwargs.pop("timeout", self.timeout)
        attempts = 3
        # base between 200–500ms; jitter ±50%; exponential growth; cap ~10s per try
        base_ms = random.uniform(0.2, 0.5)

        last_exc: Exception | None = None
        for i in range(1, attempts + 1):
            try:
                if _use_mock():
                    kwargs.pop("verify", None)
                    kwargs.pop("timeout", None)
                    resp = requests.request(method, url, headers=headers, **kwargs)
                else:
                    resp = self.session.request(
                        method, url, headers=headers, timeout=timeout, verify=self.verify, **kwargs
                    )
                # Raise for non-2xx; callers handle HTTPError
                resp.raise_for_status()
                return resp
            except requests.RequestException as e:  # includes HTTPError/ConnectionError
                last_exc = e
                # Retry only on transient (5xx or 429) or connection errors
                code = getattr(getattr(e, "response", None), "status_code", None)
                transient = code in {429, 500, 502, 503, 504} or code is None
                if i >= attempts or not transient:
                    raise
                # sleep with jitter
                backoff = base_ms * (2 ** (i - 1))
                # jitter between 50% and 150%
                backoff *= random.uniform(0.5, 1.5)
                # cap at ~10s
                backoff = min(backoff, 10.0)
                time.sleep(backoff)
        # should not reach here
        if last_exc:
            raise last_exc
        raise RuntimeError("unexpected_retry_logic_fallthrough")

    def get_json(self, path: str, params: Optional[Dict[str, Any]] = None, **kwargs) -> Dict[str, Any]:
        r = self.request("GET", path, params=params, **kwargs)
        return r.json()

    def post_json(self, path: str, payload: Dict[str, Any], idempotency_key: Optional[str] = None, **kwargs) -> Dict[str, Any]:
        extra_headers = kwargs.pop("headers", {}) or {}
        # Ensure idempotency key (X-Request-ID) is present for POSTs
        if idempotency_key:
            extra_headers["X-Request-ID"] = idempotency_key
        r = self.request("POST", path, json=payload, headers=extra_headers, **kwargs)
        return r.json()

    # --- Accounts -------------------------------------------------------------
    def accounts_with_details(self, consumer_id: str) -> Dict[str, Any]:
        """
        GET /consumers/{consumerId}/accounts/extendedWithDetails  (Accounts API)
        """
        return self.get_json(
            f"/consumers/{consumer_id}/accounts/extendedWithDetails",
            product=FINASTRA_PRODUCT_ACCOUNTS,
        )

    # --- Collaterals ----------------------------------------------------------
    def list_collaterals(self, account_id: Optional[str] = None, startingIndex: int = 0, pageSize: int = 50) -> Dict[str, Any]:
        # In mock mode, the API exposes /collateral (no account scoping). Tests reset state per test,
        # so returning all items is sufficient.
        if _use_mock():
            return self.get_json("/collateral", product=FINASTRA_PRODUCT_COLLATERAL)
        if account_id:
            params = {"accountId": account_id}
            return self.get_json("/collaterals", params=params, product=FINASTRA_PRODUCT_COLLATERAL)
        params = {"startingIndex": startingIndex, "pageSize": pageSize}
        return self.get_json("/collaterals", params=params, product=FINASTRA_PRODUCT_COLLATERAL)

    def get_collateral(self, collateral_id: str) -> Dict[str, Any]:
        return self.get_json(f"/collaterals/{collateral_id}", product=FINASTRA_PRODUCT_COLLATERAL)

    # --- Convenience: LTV (matches earlier helper behavior) -------------------
    def calculate_ltv(self, consumer_id: str) -> Dict[str, Any]:
        # In mock mode, query the balances endpoint directly for the provided account_id (== consumer_id in tests)
        if _use_mock():
            account_id = consumer_id
            balances_resp = self.get_json(
                f"/corporate/channels/accounts/me/v1/accounts/{account_id}/balances",
                product=FINASTRA_PRODUCT_ACCOUNTS,
            )
            booked = next((b for b in balances_resp.get("items", []) if b.get("type") == "BOOKED"), None)
            if not booked:
                raise ValueError("BOOKED balance not found")
            loan_balance = float(booked["amount"])
            collats = self.list_collaterals(account_id=account_id)
        else:
            accounts = self.accounts_with_details(consumer_id)
            if not accounts.get("items"):
                raise ValueError("No accounts found for consumer")
            account = accounts["items"][0]
            account_id = account.get("accountId") or account.get("id") or ""
            if not account_id:
                raise ValueError("Account ID missing from account payload")

            booked = next((b for b in account.get("balances", []) if b.get("type") == "BOOKED"), None)
            if not booked:
                raise ValueError("BOOKED balance not found")
            loan_balance = float(booked["amount"])
            collats = self.list_collaterals()
        total_collateral = 0.0
        for item in collats.get("items", []):
            val = (
                item.get("discountedNetCollateralAmount")
                or item.get("netCollateralAmount")
                or item.get("estimatedValue")
                or item.get("valuation")  # mock payload key
                or 0.0
            )
            try:
                total_collateral += float(val)
            except Exception:
                continue
        if total_collateral <= 0.0:
            raise ValueError("Total collateral valuation is zero")
        return {
            "account_id": account_id,
            "loan_balance": loan_balance,
            "total_collateral": total_collateral,
            "ltv": loan_balance / total_collateral,
        }

    # --- Payments (scaffolding) ----------------------------------------------
    def payments_initiate(self, payload: Dict[str, Any], idempotency_key: Optional[str] = None) -> Dict[str, Any]:
        """
        POST /payments
        Adds X-Request-ID idempotency by default (or uses the provided key).
        Emits Prometheus metrics.
        """
        op = "initiate"
        start = time.perf_counter()
        status = "ERR"
        try:
            data = self.post_json("/payments", payload, idempotency_key=idempotency_key, product=FINASTRA_PRODUCT_PAYMENTS)
            status = "200"
            return data
        except requests.HTTPError as e:
            try:
                status = str(e.response.status_code)
            except Exception:
                status = "ERR"
            raise
        finally:
            _payments_initiate_total.labels(result=("success" if status=="200" else "error")).inc()
            if status != "200":
                _non_2xx_total.labels(status_bucket=status[0]+"xx").inc()
            _latency_hist.observe(time.perf_counter() - start)

    def payments_status(self, payment_id: str) -> Dict[str, Any]:
        """
        GET /payments/{id}
        """
        op = "status"
        start = time.perf_counter()
        status = "ERR"
        try:
            data = self.get_json(f"/payments/{payment_id}", product=FINASTRA_PRODUCT_PAYMENTS)
            status = "200"
            return data
        except requests.HTTPError as e:
            try:
                status = str(e.response.status_code)
            except Exception:
                status = "ERR"
            raise
        finally:
            _payments_status_total.labels(result=("success" if status=="200" else "error")).inc()
            if status != "200":
                _non_2xx_total.labels(status_bucket=status[0]+"xx").inc()
            _latency_hist.observe(time.perf_counter() - start)

    # --- Loans (scaffolding) --------------------------------------------------
    def loans_get(self, loan_id: str) -> Dict[str, Any]:
        op = "get"
        start = time.perf_counter()
        status = "ERR"
        try:
            data = self.get_json(f"/loans/{loan_id}", product=FINASTRA_PRODUCT_LOANS)
            status = "200"
            return data
        except requests.HTTPError as e:
            try:
                status = str(e.response.status_code)
            except Exception:
                status = "ERR"
            raise
        finally:
            _loans_read_total.labels(endpoint=op, result=("success" if status=="200" else "error")).inc()
            _latency_hist.observe(time.perf_counter() - start)

    def loans_list(self, startingIndex: int = 0, pageSize: int = 50) -> Dict[str, Any]:
        op = "list"
        start = time.perf_counter()
        status = "ERR"
        try:
            data = self.get_json("/loans", params={"startingIndex": startingIndex, "pageSize": pageSize}, product=FINASTRA_PRODUCT_LOANS)
            status = "200"
            return data
        except requests.HTTPError as e:
            try:
                status = str(e.response.status_code)
            except Exception:
                status = "ERR"
            raise
        finally:
            _loans_read_total.labels(endpoint=op, result=("success" if status=="200" else "error")).inc()
            _latency_hist.observe(time.perf_counter() - start)

    def collaterals_for_account(self, account_id: str) -> Dict[str, Any]:
        """Get collaterals for a specific account."""
        op = "collaterals"
        start = time.perf_counter()
        status = "ERR"
        try:
            data = self.get_json(f"/accounts/{account_id}/collaterals", product=FINASTRA_PRODUCT_COLLATERAL)
            status = "200"
            return data
        except requests.HTTPError as e:
            try:
                status = str(e.response.status_code)
            except Exception:
                status = "ERR"
            raise
        finally:
            _collateral_read_total.labels(endpoint=op, result=("success" if status=="200" else "error")).inc()
            _latency_hist.observe(time.perf_counter() - start)

    def add_collateral(self, collateral_data: Dict[str, Any]) -> Dict[str, Any]:
        """Add collateral for testing purposes."""
        op = "add"
        start = time.perf_counter()
        status = "ERR"
        try:
            # Mock API expects POST /collateral
            path = "/collateral" if _use_mock() else "/collaterals"
            data = self.post_json(path, collateral_data, product=FINASTRA_PRODUCT_COLLATERAL)
            status = "200"
            return data
        except requests.HTTPError as e:
            try:
                status = str(e.response.status_code)
            except Exception:
                status = "ERR"
            raise
        finally:
            _collateral_read_total.labels(endpoint=op, result=("success" if status=="200" else "error")).inc()
            _latency_hist.observe(time.perf_counter() - start)
