"""Provider interface definitions for credit actions (Sprint 7 / PR-2).

All adapters must implement the `CreditProvider` protocol so they can be
swapped via FastAPI dependency injection.
"""

from __future__ import annotations

import abc
from typing import Any, Dict, Protocol, TypedDict

__all__ = ["ProviderResult", "CreditProvider"]


class ProviderResult(TypedDict, total=False):
    """Return payload from provider adapters.

    Keys are optional because specific providers might return less data.
    """

    provider_ref: str  # opaque reference/id returned by provider
    raw: Dict[str, Any]  # raw provider response for debugging


class CreditProvider(Protocol):
    """Protocol for credit facility providers (draw / repay / status)."""

    async def send_draw(
        self, bank_id: str, amount: float, currency: str, idem: str
    ) -> ProviderResult:
        ...

    async def send_repay(
        self, bank_id: str, amount: float, currency: str, idem: str
    ) -> ProviderResult:
        ...

    async def get_status(self, bank_id: str) -> dict:
        ...
