"""Liquidity policy engine.

All helpers are pure and deterministic so they can be unit-tested without
side-effects.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import List, Set, Tuple, TypedDict

__all__ = [
    "LiquidityPolicy",
    "compute_buffer",
    "is_holiday",
    "evaluate",
]


@dataclass(slots=True)
class LiquidityPolicy:
    """Rules for minimum liquidity and draw guardrails.

    Attributes
    ----------
    min_cash_bps
        Minimum cash buffer expressed in basis points of total available cash
        (e.g. ``500`` = 5 %).
    max_draw_bps
        Maximum allowed draw size as % (bps) of *available* cash. If the caller
        requests a draw larger than this cap, the engine will reject or reduce
        it.
    settlement_calendar
        ISO-8601 calendar dates (``YYYY-MM-DD``) that are considered holidays.
    """

    min_cash_bps: int = 0  # 1 bp = 0.01 %
    max_draw_bps: int = 10_000  # default 100 %
    settlement_calendar: Set[str] | None = None

    def as_tuple(self) -> Tuple[int, int, Tuple[str, ...]]:
        cal = tuple(sorted(self.settlement_calendar or ()))
        return (self.min_cash_bps, self.max_draw_bps, cal)


class EvaluationResult(TypedDict):
    ok: bool
    reasons: List[str]
    allowed_draw_usd: float


# ---------------------------------------------------------------------------
# Pure helpers
# ---------------------------------------------------------------------------

def compute_buffer(available_cash_usd: float, min_cash_bps: int) -> float:
    """Return the *required* cash buffer in USD."""
    return round(available_cash_usd * (min_cash_bps / 10_000), 2)


def is_holiday(asof_date: date, settlement_calendar: Set[str] | None = None) -> bool:
    """True if *asof_date* is in the calendar set (ISO string match)."""
    if not settlement_calendar:
        return False
    return asof_date.isoformat() in settlement_calendar


# ---------------------------------------------------------------------------
# Main evaluation function
# ---------------------------------------------------------------------------

def evaluate(
    policy: LiquidityPolicy,
    *,
    available_cash_usd: float,
    requested_draw_usd: float = 0.0,
    asof: date | None = None,
) -> EvaluationResult:
    """Evaluate *policy* against a snapshot.

    Parameters
    ----------
    policy : LiquidityPolicy
    available_cash_usd : float
        Current available cash.
    requested_draw_usd : float
        Amount the caller wishes to draw (optional – 0 means just a buffer
        check).
    asof : date | None
        Business date for holiday evaluation. Defaults to today (UTC).
    """
    if asof is None:
        asof = date.today()

    reasons: list[str] = []

    # Holiday rule
    if is_holiday(asof, policy.settlement_calendar):
        reasons.append("holiday")

    # Buffer rule
    buffer_req = compute_buffer(available_cash_usd, policy.min_cash_bps)
    if available_cash_usd - requested_draw_usd < buffer_req:
        reasons.append("min_buffer")

    # Max-draw rule
    max_allowed_draw = available_cash_usd * (policy.max_draw_bps / 10_000)
    if requested_draw_usd > max_allowed_draw:
        reasons.append("max_draw_cap")

    ok = len(reasons) == 0
    allowed_draw = 0.0 if not ok else min(requested_draw_usd, max_allowed_draw)

    return {
        "ok": ok,
        "reasons": reasons,
        "allowed_draw_usd": round(allowed_draw, 2),
    }
