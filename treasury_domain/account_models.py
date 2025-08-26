from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Optional

from sqlalchemy import Numeric
from sqlmodel import Column, DateTime, Field, SQLModel, func, Index

__all__ = [
    "AccountRecord",
    "BalanceRecord",
]


class _Timestamps(SQLModel):
    """Mixin adding created_ts/updated_ts with server defaults."""

    created_ts: datetime = Field(  # type: ignore[assignment]
        sa_column=Column(
            DateTime(timezone=True),
            server_default=func.now(),
            nullable=False,
        )
    )
    updated_ts: datetime = Field(  # type: ignore[assignment]
        sa_column=Column(
            DateTime(timezone=True),
            server_default=func.now(),
            onupdate=func.now(),
            nullable=False,
        )
    )


class AccountRecord(SQLModel, table=True):
    """Persisted account metadata from Finastra."""

    __tablename__ = "fin_accounts"
    __table_args__ = (
        Index("idx_accounts_provider_ext", "provider", "external_id", unique=True),
    )

    id: Optional[int] = Field(default=None, primary_key=True)
    provider: str = Field(default="finastra", nullable=False, index=True)
    external_id: str = Field(nullable=False)

    account_number: Optional[str] = None
    iban: Optional[str] = None
    currency: Optional[str] = None  # 3-letter ISO
    context: Optional[str] = None
    type: Optional[str] = None
    status: Optional[str] = None

    external_updated_ts: Optional[datetime] = Field(default=None)
    source_hash: Optional[str] = Field(max_length=64, index=True)

    # timestamps
    created_ts: datetime = Field(  # type: ignore[assignment]
        sa_column=Column(
            DateTime(timezone=True),
            server_default=func.now(),
            nullable=False,
        )
    )
    updated_ts: datetime = Field(  # type: ignore[assignment]
        sa_column=Column(
            DateTime(timezone=True),
            server_default=func.now(),
            onupdate=func.now(),
            nullable=False,
        )
    )


class BalanceRecord(SQLModel, table=True):
    """Persisted balances per account at point-in-time."""

    __tablename__ = "fin_balances"
    __table_args__ = (
        Index("idx_balances_provider_acct_ts", "provider", "account_external_id", "as_of_ts"),
    )

    id: Optional[int] = Field(default=None, primary_key=True)
    provider: str = Field(default="finastra", nullable=False, index=True)

    account_external_id: str = Field(nullable=False)
    as_of_ts: datetime = Field(nullable=False)

    current_amount: Decimal = Field(sa_column=Column(Numeric(20, 4), nullable=False))
    available_amount: Optional[Decimal] = Field(default=None, sa_column=Column(Numeric(20, 4)))
    credit_limit_amount: Optional[Decimal] = Field(default=None, sa_column=Column(Numeric(20, 4)))
    currency: Optional[str] = None

    source_hash: Optional[str] = Field(max_length=64, index=True)

    created_ts: datetime = Field(  # type: ignore[assignment]
        sa_column=Column(
            DateTime(timezone=True),
            server_default=func.now(),
            nullable=False,
        )
    )
    updated_ts: datetime = Field(  # type: ignore[assignment]
        sa_column=Column(
            DateTime(timezone=True),
            server_default=func.now(),
            onupdate=func.now(),
            nullable=False,
        )
    )
