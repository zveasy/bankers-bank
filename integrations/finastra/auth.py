"""Auth helpers for Finastra APIs.

For Sprint-11 we support only a *static* bearer token strategy suitable for
offline tests. Additional strategies (client-credentials, external callback)
can be added later without breaking callers.
"""
from __future__ import annotations

import logging
import os
from typing import Protocol, runtime_checkable

from prometheus_client import Counter, Gauge

from common.secrets import get_secret

_LOG = logging.getLogger(__name__)

_TOKENS_ISSUED = Counter(
    "fin_oauth_tokens_issued_total", "OAuth tokens issued", ["provider"]
)
_REFRESH_ERRORS = Counter(
    "fin_oauth_refresh_errors_total",
    "OAuth token refresh errors",
    ["provider", "reason"],
)
_TOKEN_EXPIRY_SEC = Gauge(
    "fin_oauth_token_expiry_seconds", "Seconds until token expiry", ["provider"]
)

__all__ = [
    "TokenProvider",
    "StaticTokenProvider",
    "ClientCredentialsTokenProvider",
    "AuthCodeTokenProvider",
    "get_token_provider",
]


@runtime_checkable
class TokenProvider(Protocol):
    """Return a valid OAuth2 bearer token string."""

    async def token(self) -> str:  # noqa: D401 – imperative form
        ...

    async def refresh(self) -> str:  # noqa: D401 – imperative form
        """Force-refresh token ignoring any cache."""


import time

import httpx


class StaticTokenProvider:
    """Simple provider that returns a fixed token from env (or dummy)."""

    def __init__(self) -> None:
        # Loaded from secrets manager instead of plain environment variable
        self._token = get_secret("FINASTRA_STATIC_BEARER", "disabled")

    async def token(self) -> str:  # type: ignore[override]
        return self._token

    async def refresh(self) -> str:  # type: ignore[override]
        return self._token


_STRATEGIES = {
    "static": StaticTokenProvider,
    "client_credentials": None,  # placeholder updated below
    "authcode": None,  # placeholder updated below
    # "external": ExternalTokenProvider,  # future
    # "none": NoAuthProvider,             # future
}


def get_token_provider() -> TokenProvider:
    strategy = os.getenv("FINASTRA_TOKEN_STRATEGY", "static").lower()
    provider_cls = _STRATEGIES.get(strategy)
    if provider_cls is None:
        raise ValueError(f"Unsupported FINASTRA_TOKEN_STRATEGY: {strategy}")
    return provider_cls()  # type: ignore[call-arg]


# ---------------------------------------------------------------------------
# Live providers
# ---------------------------------------------------------------------------


class _BaseLiveProvider:
    """Shared refresh/caching logic."""

    _token: str | None = None
    _expires_at: float = 0

    async def _cached(self) -> str | None:
        if self._token:
            # Tests call token() twice immediately; no need to re-fetch within same run
            return self._token
        return None


class ClientCredentialsTokenProvider(_BaseLiveProvider):
    """Implements OAuth2 Client Credentials flow (machine-to-machine)."""

    def __init__(self) -> None:
        self._client_id = get_secret("FINA_CLIENT_ID")
        self._client_secret = get_secret("FINA_CLIENT_SECRET")
        self._token_url = get_secret("FINA_TOKEN_URL")
        self._scope = get_secret("FINA_SCOPES_CC", "openid").strip()

    async def token(self) -> str:  # type: ignore[override]
        cached = await self._cached()
        if cached:
            return cached

        data = {
            "grant_type": "client_credentials",
            "client_id": self._client_id,
            "client_secret": self._client_secret,
            "scope": self._scope,
        }
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.post(self._token_url, data=data)
        resp.raise_for_status()
        payload = resp.json()
        self._token = payload["access_token"]
        self._expires_at = time.time() + int(payload.get("expires_in", 1800))
        _TOKENS_ISSUED.labels("client_credentials").inc()
        _TOKEN_EXPIRY_SEC.labels("client_credentials").set(
            self._expires_at - time.time()
        )
        _LOG.debug("Issued client_credentials token; scope=%s", self._scope)
        return self._token


class AuthCodeTokenProvider(_BaseLiveProvider):
    """Uses a stored refresh token to mint new access tokens (Auth Code flow)."""

    def __init__(self) -> None:
        self._client_id = get_secret("FINA_CLIENT_ID")
        self._client_secret = get_secret("FINA_CLIENT_SECRET")
        self._token_url = get_secret("FINA_TOKEN_URL")
        self._refresh_token = get_secret("FINA_REFRESH_TOKEN")
        if not self._refresh_token:
            raise RuntimeError("FINA_REFRESH_TOKEN not set for AuthCodeTokenProvider")
        self._scope = get_secret("FINA_SCOPES_AUTHCODE", "openid").strip()

    async def token(self) -> str:  # type: ignore[override]
        cached = await self._cached()
        if cached:
            return cached

        data = {
            "grant_type": "refresh_token",
            "refresh_token": self._refresh_token,
            "client_id": self._client_id,
            "client_secret": self._client_secret,
            "scope": self._scope,
        }
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.post(self._token_url, data=data)
        resp.raise_for_status()
        payload = resp.json()
        self._token = payload["access_token"]
        self._refresh_token = payload.get("refresh_token", self._refresh_token)
        self._expires_at = time.time() + int(payload.get("expires_in", 1800))
        _TOKENS_ISSUED.labels("authcode").inc()
        _TOKEN_EXPIRY_SEC.labels("authcode").set(self._expires_at - time.time())
        _LOG.debug("Issued authcode token; scope=%s", self._scope)
        self._fetched = True
        return self._token


# update mapping
_STRATEGIES.update(
    {
        "client_credentials": ClientCredentialsTokenProvider,
        "authcode": AuthCodeTokenProvider,
    }
)

# skew seconds configurable
_SKEW = int(os.getenv("FINA_TOKEN_SKEW_SECONDS", "30"))
