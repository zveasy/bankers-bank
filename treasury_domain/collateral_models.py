"""Domain + persistence models for external collateral data (Sprint-11).

We keep domain DTO (`FinastraCollateral`) separate from persistence (`CollateralRecord`).
This ensures future providers can map into the same table without leaking API-specific
fields.
"""
from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Any, Dict, Optional

from sqlalchemy import Column, DateTime, Index, JSON, Numeric, String, UniqueConstraint
from sqlmodel import Field, SQLModel


class FinastraCollateral(SQLModel):
    """Data-transfer object matching Finastra collateral payload (subset)."""

    id: str
    kind: Optional[str] = None
    status: Optional[str] = None
    currency: Optional[str] = None
    amount: Optional[Decimal] = None
    valuation_ts: Optional[datetime] = None
    external_updated_ts: Optional[datetime] = None
    bank_id: Optional[str] = None
    raw: Dict[str, Any]


class CollateralRecord(SQLModel, table=True):
    """SQLModel table storing latest collateral snapshot per ID."""

    id: str = Field(sa_column=Column("id", String, primary_key=True))
    bank_id: Optional[str] = Field(default=None, sa_column=Column("bank_id", String))
    kind: Optional[str] = Field(default=None, sa_column=Column("kind", String))
    status: Optional[str] = Field(default=None, sa_column=Column("status", String))
    currency: Optional[str] = Field(default=None, sa_column=Column("currency", String(3)))
    amount: Optional[Decimal] = Field(default=None, sa_column=Column("amount", Numeric(18, 2)))
    valuation_ts: Optional[datetime] = Field(default=None, sa_column=Column("valuation_ts", DateTime))
    external_updated_ts: Optional[datetime] = Field(
        default=None, sa_column=Column("external_updated_ts", DateTime)
    )
    raw: Dict[str, Any] = Field(default={}, sa_column=Column("raw", JSON, nullable=False))
    source_hash: Optional[str] = Field(default=None, sa_column=Column("source_hash", String(64)))
    created_at: datetime = Field(default_factory=datetime.utcnow, sa_column=Column(DateTime))
    updated_at: datetime = Field(
        default_factory=datetime.utcnow,
        sa_column=Column(DateTime, onupdate=datetime.utcnow),
    )

    __table_args__ = (
        UniqueConstraint("bank_id", "id", name="collateral_bank_id_uniq"),
        Index("ix_collateral_external_updated", "external_updated_ts"),
    )
