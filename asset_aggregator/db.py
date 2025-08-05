from __future__ import annotations

import os
from datetime import datetime
from typing import Optional

from sqlmodel import SQLModel, Field, create_engine, Session
from sqlalchemy import Column, String, DateTime, Float

DATABASE_URL = os.getenv("ASSET_DB_URL", "sqlite:///./asset_aggregator.db")
engine = create_engine(DATABASE_URL, echo=False)


class AssetSnapshot(SQLModel, table=True):
    """Database model representing a snapshot of a bank's assets."""

    id: Optional[int] = Field(default=None, primary_key=True)
    bank_id: str = Field(sa_column=Column("bank_id", String, nullable=False))
    ts: datetime = Field(sa_column=Column("ts", DateTime, nullable=False))
    # Explicit Postgres column names (all lowercase) to match raw SQL inserts
    eligibleCollateralUSD: float = Field(default=0.0, sa_column=Column("eligiblecollateralusd", Float, nullable=True))
    totalBalancesUSD: float = Field(default=0.0, sa_column=Column("totalbalancesusd", Float, nullable=True))
    undrawnCreditUSD: float = Field(default=0.0, sa_column=Column("undrawncreditusd", Float, nullable=True))


from sqlalchemy import text

def init_db() -> None:
    """Initialise tables, dropping old incompatible schema first."""
    with engine.begin() as conn:
        conn.exec_driver_sql("DROP TABLE IF EXISTS assetsnapshot CASCADE;")
    SQLModel.metadata.create_all(engine)


def get_session() -> Session:
    return Session(engine)
