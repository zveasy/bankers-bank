"""Auth helpers for Finastra APIs.

For Sprint-11 we support only a *static* bearer token strategy suitable for
offline tests. Additional strategies (client-credentials, external callback)
can be added later without breaking callers.
"""
from __future__ import annotations

import os
from typing import Protocol, runtime_checkable

__all__ = ["TokenProvider", "StaticTokenProvider", "get_token_provider"]


@runtime_checkable
class TokenProvider(Protocol):
    """Return a valid OAuth2 bearer token string."""

    async def token(self) -> str:  # noqa: D401 – imperative form
        ...


class StaticTokenProvider:
    """Simple provider that returns a fixed token from env (or dummy)."""

    def __init__(self) -> None:
        self._token = os.getenv("FINASTRA_STATIC_BEARER", "disabled")

    async def token(self) -> str:  # type: ignore[override]
        return self._token


_STRATEGIES = {
    "static": StaticTokenProvider,
    # "external": ExternalTokenProvider,  # future
    # "none": NoAuthProvider,             # future
}


def get_token_provider() -> TokenProvider:
    strategy = os.getenv("FINASTRA_TOKEN_STRATEGY", "static").lower()
    provider_cls = _STRATEGIES.get(strategy)
    if provider_cls is None:
        raise ValueError(f"Unsupported FINASTRA_TOKEN_STRATEGY: {strategy}")
    return provider_cls()  # type: ignore[call-arg]
