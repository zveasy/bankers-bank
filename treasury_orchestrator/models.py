"""Data models for Treasury Orchestrator."""

from datetime import datetime
from decimal import Decimal
from pydantic import BaseModel, ConfigDict


class RiskChecks(BaseModel):
    """Risk check parameters and results."""
    var_limit_bps: int
    observed_var_bps: int


class SweepOrder(BaseModel):
    """Sweep order model."""
    model_config = ConfigDict(
        json_encoders={
            Decimal: str,
            datetime: lambda v: v.isoformat()
        }
    )
    
    order_id: str
    source_account: str
    target_product: str
    amount_usd: Decimal
    cutoff_utc: datetime
    risk_checks: RiskChecks
    created_ts: datetime
