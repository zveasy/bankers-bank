from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Optional

from sqlalchemy import UniqueConstraint, Numeric
from sqlalchemy.types import JSON
from sqlmodel import SQLModel, Field, Column, DateTime, func, Index

__all__ = ["AccountTransactionRecord"]


class AccountTransactionRecord(SQLModel, table=True):
    """Persisted transactions per account from Finastra Account Information US."""

    __tablename__ = "fin_account_transactions"
    __table_args__ = (
        UniqueConstraint(
            "provider",
            "account_external_id",
            "external_tx_id",
            "booking_date",
            name="uq_tx_provider_acct_extid_booking",
        ),
        Index("ix_tx_acct_booking", "account_external_id", "booking_date"),
        Index("ix_tx_last_seen", "last_seen_ts"),
    )

    id: Optional[int] = Field(default=None, primary_key=True)

    provider: str = Field(default="finastra", nullable=False, index=True, max_length=64)
    account_external_id: str = Field(nullable=False, index=True, max_length=128)

    external_tx_id: str = Field(nullable=False, index=True, max_length=128)
    booking_date: datetime = Field(nullable=False)
    value_date: Optional[datetime] = None

    direction: str = Field(nullable=False, max_length=2)
    status: Optional[str] = Field(default=None, max_length=32)

    amount: Decimal = Field(sa_column=Column(Numeric(20, 4), nullable=False))
    currency: str = Field(nullable=False, max_length=3)

    description: Optional[str] = Field(default=None, max_length=2048)
    reference: Optional[str] = Field(default=None, max_length=256)

    counterparty_name: Optional[str] = Field(default=None, max_length=256)
    counterparty_account: Optional[str] = Field(default=None, max_length=64)

    scheme: Optional[str] = Field(default=None, max_length=32)
    category: Optional[str] = Field(default=None, max_length=64)

    fx_rate: Optional[Decimal] = Field(default=None, sa_column=Column(Numeric(20, 10)))
    fx_src_ccy: Optional[str] = Field(default=None, max_length=3)
    fx_dst_ccy: Optional[str] = Field(default=None, max_length=3)
    fx_dst_amount: Optional[Decimal] = Field(default=None, sa_column=Column(Numeric(20, 4)))

    source_hash: str = Field(nullable=False, index=True, max_length=64)
    raw_json: Optional[dict] = Field(default=None, sa_column=Column(JSON))

    inserted_ts: datetime = Field(  # type: ignore[assignment]
        sa_column=Column(
            DateTime(timezone=True),
            server_default=func.now(),
            nullable=False,
        )
    )
    last_seen_ts: datetime = Field(  # type: ignore[assignment]
        sa_column=Column(
            DateTime(timezone=True),
            server_default=func.now(),
            onupdate=func.now(),
            nullable=False,
        ),
    )
