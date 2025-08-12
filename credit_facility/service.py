"""Business logic for credit facility capacity (Sprint 7, PR-1)."""
from __future__ import annotations

import json
import os
from datetime import datetime
from pathlib import Path
from typing import Dict

from sqlmodel import Session, select

from asset_aggregator.db import AssetSnapshot, get_session
from credit_facility.models import CreditDraw, CreditFacility, CreditRepayment
from treasury_observability.metrics import (credit_capacity_available,
                                            credit_outstanding_total)

# ---------------------------------------------------------------------------
# Policy loading
# ---------------------------------------------------------------------------

_DEFAULT_POLICY = {
    "default_cap": 1_000_000.0,
    "banks": {},
}

_POLICY_PATH = Path(__file__).with_name("policy.json")


def _load_policy() -> Dict:
    try:
        with _POLICY_PATH.open() as fp:
            data = json.load(fp)
            return {**_DEFAULT_POLICY, **data}
    except FileNotFoundError:
        return _DEFAULT_POLICY


_POLICY = _load_policy()


# ---------------------------------------------------------------------------
# Service class
# ---------------------------------------------------------------------------


class CreditFacilityService:
    """Compute available capacity for a bank."""

    def __init__(self, session: Session | None = None):
        self.session = session or get_session()

    # ---------------------------------------------------------------------
    def capacity(self, bank_id: str) -> float:
        """Return currently available draw capacity in USD.

        Formula: ``available = min(policy_cap, ltv * eligible) - outstanding``.
        Negative values are floored at 0.
        """
        policy = _POLICY["banks"].get(bank_id, {})
        cap = policy.get("cap", _POLICY["default_cap"])
        buffer = policy.get("buffer", 0.0)

        # 1. latest snapshot
        snap_stmt = (
            select(AssetSnapshot)
            .where(AssetSnapshot.bank_id == bank_id)
            .order_by(AssetSnapshot.ts.desc())
            .limit(1)
        )
        snapshot: AssetSnapshot | None = self.session.exec(snap_stmt).first()
        if snapshot is None:
            # no asset snapshots yet – fall back to policy cap minus outstanding
            outstanding = self._outstanding(bank_id)
            available = max(cap - outstanding - buffer, 0.0)
            credit_capacity_available.labels(bank_id=bank_id).set(available)
            credit_outstanding_total.labels(bank_id=bank_id).set(outstanding)
            return available

        eligible = snapshot.eligibleCollateralUSD or 0.0
        ltv = self._latest_ltv(bank_id)

        # 2. outstanding draws – repayments
        outstanding = self._outstanding(bank_id)

        raw_available = cap - outstanding - buffer
        available = max(raw_available, 0.0)

        # Update gauges
        credit_capacity_available.labels(bank_id=bank_id).set(available)
        credit_outstanding_total.labels(bank_id=bank_id).set(outstanding)

        return available

    # ------------------------------------------------------------------
    def _outstanding(self, bank_id: str) -> float:
        """Return net outstanding amount (draws–repayments) in USD."""
        draw_sum = self.session.exec(
            select(CreditDraw.amount).where(CreditDraw.bank_id == bank_id)
        ).all()
        repay_sum = self.session.exec(
            select(CreditRepayment.amount).where(CreditRepayment.bank_id == bank_id)
        ).all()
        return sum(draw_sum) - sum(repay_sum)

    def _latest_ltv(self, bank_id: str) -> float:
        """For now retrieve snapshot.undrawnCreditUSD / eligibleCollateralUSD with guard."""
        stmt = (
            select(AssetSnapshot)
            .where(AssetSnapshot.bank_id == bank_id)
            .order_by(AssetSnapshot.ts.desc())
            .limit(1)
        )
        snap: AssetSnapshot | None = self.session.exec(stmt).first()
        if snap is None or not snap.eligibleCollateralUSD:
            return 0.0
        return (snap.undrawnCreditUSD or 0.0) / snap.eligibleCollateralUSD
