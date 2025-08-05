# quantengine/models/collateral.py
from datetime import datetime
from typing import Optional

from sqlmodel import SQLModel, Field

class AssetSnapshot(SQLModel, table=True):
    """
    Immutable point-in-time view of a bank’s assets.
    Populated by asset_aggregator → Kafka → quant_consumer.
    """
    __tablename__ = "asset_snapshots"

    id: Optional[int] = Field(default=None, primary_key=True)
    bank_id: str = Field(index=True)
    asof_ts: datetime = Field(index=True)
    eligible_collateral_usd: float
    total_balances_usd: float
    undrawn_credit_usd: float

    class Config:
        frozen = True     # ↖ makes instances hashable / immutable

class CollateralRegistry(SQLModel, table=True):
    """
    Rolling ‘truth’ table for current on-book collateral per asset.
    Updated idempotently by the reconciliation job.
    """
    __tablename__ = "collateral_registry"

    asset_id: str = Field(primary_key=True)           # e.g. CUSIP / ISIN
    bank_id: str = Field(index=True)
    asof_ts: datetime                                 # last verified timestamp
    asset_type: str
    market_value_usd: float
    haircut_pct: float                                # e.g. 0.15 means 85 % LTV
    is_eligible: bool = Field(default=True)

    @property
    def eligible_value(self) -> float:
        return 0.0 if not self.is_eligible else self.market_value_usd * (1 - self.haircut_pct)

class LtvHistory(SQLModel, table=True):
    """
    Historical Loan-to-Value ratio per bank.
    Written once per snapshot ingest for charting & alerts.
    """
    __tablename__ = "ltv_history"

    id: Optional[int] = Field(default=None, primary_key=True)
    bank_id: str = Field(index=True)
    ts: datetime = Field(index=True)
    ltv_ratio: float
