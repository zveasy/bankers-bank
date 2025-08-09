from datetime import datetime, timezone
from decimal import Decimal

from .models import RiskChecks, SweepOrder


class DecisionEngine:
    """
    Temporary stub: always sweeps 10 % of the balance
    to FED_RRP.  Real VaR logic comes in Sprint-2.
    """

    def decide(self, balance_usd: Decimal) -> SweepOrder:
        sweep_amt = (balance_usd * Decimal("0.10")).quantize(Decimal("0.0001"))
        now = datetime.now(tz=timezone.utc)

        return SweepOrder(
            order_id="01HX6TESTSTUBENGINE0000000000",  # replace with ULID later
            source_account="0123456789",
            target_product="FED_RRP",
            amount_usd=sweep_amt,
            cutoff_utc=now,
            risk_checks=RiskChecks(var_limit_bps=10, observed_var_bps=5),
            created_ts=now,
        )
