from __future__ import annotations

import os
from datetime import datetime
from typing import Optional

from sqlalchemy import (Column, DateTime, Float, Index, String,
                        UniqueConstraint, text)
from sqlmodel import Field, Session, SQLModel, create_engine
from sqlmodel import Session as _AuditSession  # audit
from common.audit import log_event, get_engine as _audit_engine  # audit

DATABASE_URL = os.getenv("ASSET_DB_URL", "sqlite:///./asset_aggregator.db")
engine = create_engine(DATABASE_URL, echo=False)


class AssetSnapshot(SQLModel, table=True):
    """Database model representing a snapshot of a bank's assets."""

    id: Optional[int] = Field(default=None, primary_key=True)
    bank_id: str = Field(sa_column=Column("bank_id", String, nullable=False))
    ts: datetime = Field(sa_column=Column("ts", DateTime, nullable=False))
    # Explicit Postgres column names (all lowercase) to match raw SQL inserts
    eligibleCollateralUSD: float = Field(
        default=0.0, sa_column=Column("eligiblecollateralusd", Float, nullable=True)
    )
    totalBalancesUSD: float = Field(
        default=0.0, sa_column=Column("totalbalancesusd", Float, nullable=True)
    )
    undrawnCreditUSD: float = Field(
        default=0.0, sa_column=Column("undrawncreditusd", Float, nullable=True)
    )

    # Allow multiple snapshots for same bank_id & ts during tests; keep non-unique index for query perf.
    __table_args__ = (
        Index("ix_asset_snapshots_bank_ts", "bank_id", "ts"),
    )


from sqlalchemy import text


def init_db() -> None:
    """Initialise tables (idempotent)."""
    SQLModel.metadata.create_all(engine)


# ---- New Sprint 6 tables ----
class CollateralRegistry(SQLModel, table=True):
    """Registry of collateral positions keyed by (bank_id, collateral_id)."""

    id: Optional[int] = Field(default=None, primary_key=True)
    bank_id: str = Field(sa_column=Column("bank_id", String, nullable=False))
    collateral_id: str = Field(
        sa_column=Column("collateral_id", String, nullable=False)
    )
    description: Optional[str] = Field(
        default=None, sa_column=Column("description", String)
    )
    amountUSD: Optional[float] = Field(
        default=None, sa_column=Column("amountusd", Float)
    )

    __table_args__ = (
        UniqueConstraint("bank_id", "collateral_id", name="collateral_registry_uniq"),
    )


class LTVHistory(SQLModel, table=True):
    """Historical LTV data keyed by (bank_id, ts)."""

    id: Optional[int] = Field(default=None, primary_key=True)
    bank_id: str = Field(sa_column=Column("bank_id", String, nullable=False))
    ts: datetime = Field(sa_column=Column("ts", DateTime, nullable=False))
    ltv: Optional[float] = Field(default=None, sa_column=Column("ltv", Float))
    __table_args__ = (UniqueConstraint("bank_id", "ts", name="ltv_history_uniq"),)


# ---- helper upsert ----


def upsert_assetsnapshot(
    session: Session, bank_id: str, ts, ec_usd, tb_usd, uc_usd
) -> None:
    """Idempotent upsert for AssetSnapshot using ON CONFLICT."""
    session.exec(
        text(
            """
            INSERT INTO assetsnapshot (bank_id, ts, eligiblecollateralusd, totalbalancesusd, undrawncreditusd)
            VALUES (:bank_id, :ts, :ec, :tb, :uc)
            ON CONFLICT (bank_id, ts) DO UPDATE SET
              eligiblecollateralusd = EXCLUDED.eligiblecollateralusd,
              totalbalancesusd      = EXCLUDED.totalbalancesusd,
              undrawncreditusd      = EXCLUDED.undrawncreditusd
            """
        ).bindparams(bank_id=bank_id, ts=ts, ec=ec_usd, tb=tb_usd, uc=uc_usd)
    )
    session.commit()

    # --- Audit log ---
    with _AuditSession(_audit_engine()) as _aud_sess:
        log_event(
            session=_aud_sess,
            service="asset_aggregator",
            action="ASSET_SNAPSHOT_UPSERTED",
            actor=bank_id,
            details={
                "ts": ts.isoformat() if hasattr(ts, 'isoformat') else str(ts),
                "eligibleCollateralUSD": ec_usd,
                "totalBalancesUSD": tb_usd,
                "undrawnCreditUSD": uc_usd,
            },
        )


def get_session() -> Session:
    return Session(engine)
