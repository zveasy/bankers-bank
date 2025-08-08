"""Mock Finastra provider adapter (Sprint 7 / PR-2).

Simulates asynchronous provider calls without external network access.
Failures can be injected via the ``MOCK_PROVIDER_FAIL`` env variable
(one of: "draw", "repay").
"""

from __future__ import annotations

import asyncio
import os
from typing import Any, Dict
from uuid import uuid4

from .base import CreditProvider, ProviderResult

_FAIL_FLAG = os.getenv("MOCK_PROVIDER_FAIL", "")
_LATENCY_SEC = float(os.getenv("MOCK_PROVIDER_LATENCY", "0.05"))


class MockFinastra(CreditProvider):
    """Simple in-memory mock implementing ``CreditProvider``."""

    async def _maybe_fail(self, action: str):
        if _FAIL_FLAG == action:
            raise RuntimeError(f"mock provider forced failure for {action}")

    async def send_draw(
        self, bank_id: str, amount: float, currency: str, idem: str
    ) -> ProviderResult:  # noqa: D401,E501
        await asyncio.sleep(_LATENCY_SEC)
        await self._maybe_fail("draw")
        return {
            "provider_ref": f"mock-{uuid4()}",
            "raw": {
                "action": "draw",
                "bank_id": bank_id,
                "amount": amount,
                "currency": currency,
                "idempotency": idem,
            },
        }

    async def send_repay(
        self, bank_id: str, amount: float, currency: str, idem: str
    ) -> ProviderResult:  # noqa: D401,E501
        await asyncio.sleep(_LATENCY_SEC)
        await self._maybe_fail("repay")
        return {
            "provider_ref": f"mock-{uuid4()}",
            "raw": {
                "action": "repay",
                "bank_id": bank_id,
                "amount": amount,
                "currency": currency,
                "idempotency": idem,
            },
        }

    async def get_status(self, bank_id: str) -> Dict[str, Any]:
        # Return a very simple canned status
        await asyncio.sleep(_LATENCY_SEC)
        return {"bank_id": bank_id, "status": "OK", "provider": self.provider_name}
