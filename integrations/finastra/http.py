"""Shared HTTP helpers for Finastra REST APIs (offline-friendly).

Uses `httpx.AsyncClient` with:
* Base URL from env vars (see `integrations.finastra`)
* Automatic bearer-token injection via `TokenProvider`
* Simple exponential back-off retry on 429 / 5xx (max 3 retries)
* Prometheus counters + histogram (labels: product, endpoint, method, status)

Network access is *never* used in CI; tests patch the transport to `MockTransport`.
"""
from __future__ import annotations

import asyncio
import time
from typing import Any, Callable, Dict, Optional

import httpx
import random
import logging
from prometheus_client import Counter, Histogram

from . import BASE_URL
from .auth import TokenProvider, get_token_provider

__all__ = ["FinastraHTTP"]

_LOG = logging.getLogger(__name__)

import os

from .auth import (
    AuthCodeTokenProvider,
    ClientCredentialsTokenProvider,
    StaticTokenProvider,
)

_REQUESTS_TOTAL = Counter(
    "fin_http_requests_total",
    "HTTP requests to Finastra",
    labelnames=["product", "endpoint", "method", "status"],
)
_LATENCY_SEC = Histogram(
    "fin_http_latency_seconds",
    "Latency for Finastra HTTP requests",
    labelnames=["product", "endpoint"],
)


class FinastraHTTP:
    def __init__(
        self,
        *,
        product: str = "unknown",
        base_url: str = BASE_URL,
        token_provider: Optional[TokenProvider] = None,
        transport: Optional[httpx.AsyncBaseTransport] = None,
    ):
        # pick provider if none supplied
        if token_provider is None:
            env_key = f"FINA_FLOW_{product.upper().replace('-', '_')}"
            flow = os.getenv(env_key, "static").lower()
            if flow == "client_credentials":
                token_provider = ClientCredentialsTokenProvider()
            elif flow in {"authcode", "auth_code"}:
                token_provider = AuthCodeTokenProvider()
            else:
                token_provider = StaticTokenProvider()
        self._token_provider = token_provider
        if 'flow' not in locals():
            # derive flow from supplied provider
            if isinstance(token_provider, ClientCredentialsTokenProvider):
                flow = "client_credentials"
            elif isinstance(token_provider, AuthCodeTokenProvider):
                flow = "authcode"
            elif isinstance(token_provider, StaticTokenProvider):
                flow = "static"
            else:
                flow = token_provider.__class__.__name__
        self._product = product
        # debug log (product, flow, scopes)
        scope = getattr(self._token_provider, "_scope", "n/a")
        _LOG.debug("OAuth resolved: product=%s flow=%s scopes=%s", product, flow, scope)
        self._client = httpx.AsyncClient(base_url=base_url, timeout=10, transport=transport)

    async def _request(self, method: str, url: str, **kwargs) -> httpx.Response:  # noqa: D401 – imperative
        headers_template = kwargs.pop("headers", {})
        attempt = 0
        refreshed = False
        while True:
            token = await self._token_provider.token()
            headers = {**headers_template, "Authorization": f"Bearer {token}"}
            endpoint_label = url.split("?", 1)[0]

            attempt += 1
            start = time.perf_counter()
            try:
                resp = await self._client.request(method, url, headers=headers, **kwargs)
            except httpx.RequestError as exc:
                if attempt >= 3:
                    raise
                await asyncio.sleep(2 ** attempt * 0.1)
                continue
            elapsed = time.perf_counter() - start
            _LATENCY_SEC.labels(self._product, endpoint_label).observe(elapsed)
            _REQUESTS_TOTAL.labels(self._product, endpoint_label, method.lower(), resp.status_code).inc()
            if resp.status_code in {429, 502, 503, 504} and attempt < 3:
                retry_after = resp.headers.get("Retry-After")
                delay = float(retry_after) if retry_after and retry_after.isdigit() else 2 ** attempt * 0.1
                delay = delay * (1 + random.random() * 0.2)  # jitter ±20%
                await asyncio.sleep(delay)
                continue
            if resp.status_code == 401 and not refreshed:
                # token likely expired; refresh provider and retry once
                try:
                    await self._token_provider.refresh()
                except Exception:
                    # refresh errors already counted by provider metrics
                    resp.raise_for_status()
                refreshed = True
                continue
            resp.raise_for_status()
            return resp

    async def get(self, url: str, **kw) -> httpx.Response:  # noqa: D401 – imperative
        return await self._request("GET", url, **kw)

    async def aclose(self) -> None:
        await self._client.aclose()

    # context-manager sugar
    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        await self.aclose()
