from __future__ import annotations

import os
from datetime import datetime
from typing import Optional

from sqlmodel import SQLModel, Field, create_engine, Session

DATABASE_URL = os.getenv("ASSET_DB_URL", "sqlite:///./asset_aggregator.db")
engine = create_engine(DATABASE_URL, echo=False)


class AssetSnapshot(SQLModel, table=True):
    """Database model representing a snapshot of a bank's assets."""

    id: Optional[int] = Field(default=None, primary_key=True)
    bank_id: str
    ts: datetime
    eligibleCollateralUSD: float
    totalBalancesUSD: float
    undrawnCreditUSD: float


def init_db() -> None:
    """Initialise tables."""
    SQLModel.metadata.create_all(engine)


def get_session() -> Session:
    return Session(engine)
