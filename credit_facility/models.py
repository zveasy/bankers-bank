from __future__ import annotations

"""SQLModel ORM definitions for credit-facility subsystem (Sprint 7).
All column names are explicit lowercase to match raw SQL inserts.
"""

from datetime import datetime
from typing import Optional

from sqlalchemy import Column, DateTime, Float, Index, String, UniqueConstraint
from sqlmodel import Field, SQLModel


class CreditFacility(SQLModel, table=True):
    """Static limits for a bank's revolving credit facility."""

    id: Optional[int] = Field(default=None, primary_key=True)
    bank_id: str = Field(sa_column=Column("bank_id", String, nullable=False))
    currency: str = Field(
        sa_column=Column("currency", String, nullable=False, default="USD")
    )

    # policy-driven caps / buffers (all in currency units)
    cap: float = Field(sa_column=Column("cap", Float, nullable=False))
    buffer: float = Field(
        sa_column=Column("buffer", Float, nullable=False, default=0.0)
    )

    updated_at: datetime = Field(
        default_factory=datetime.utcnow,
        sa_column=Column("updated_at", DateTime, nullable=False),
    )

    __table_args__ = (UniqueConstraint("bank_id", name="credit_facility_uniq"),)


class CreditDraw(SQLModel, table=True):
    """Draw requests against a facility (idempotent via idempotency_key)."""

    id: Optional[int] = Field(default=None, primary_key=True)

    idempotency_key: str = Field(
        sa_column=Column("idempotency_key", String, nullable=False)
    )
    bank_id: str = Field(sa_column=Column("bank_id", String, nullable=False))
    amount: float = Field(sa_column=Column("amount", Float, nullable=False))
    currency: str = Field(
        sa_column=Column("currency", String, nullable=False, default="USD")
    )
    created_at: datetime = Field(
        default_factory=datetime.utcnow,
        sa_column=Column("created_at", DateTime, nullable=False),
    )

    status: str = Field(
        sa_column=Column("status", String, nullable=False, default="pending")
    )
    provider_ref: Optional[str] = Field(
        default=None, sa_column=Column("provider_ref", String)
    )

    __table_args__ = (
        UniqueConstraint("idempotency_key", "bank_id", name="credit_draw_idem_uniq"),
        Index("ix_credit_draw_bank_ts", "bank_id", "created_at"),
        {"extend_existing": True},
    )


class CreditRepayment(SQLModel, table=True):
    """Repayments against a facility."""

    id: Optional[int] = Field(default=None, primary_key=True)
    idempotency_key: str = Field(
        sa_column=Column("idempotency_key", String, nullable=False)
    )
    bank_id: str = Field(sa_column=Column("bank_id", String, nullable=False))
    amount: float = Field(sa_column=Column("amount", Float, nullable=False))
    currency: str = Field(
        sa_column=Column("currency", String, nullable=False, default="USD")
    )
    created_at: datetime = Field(
        default_factory=datetime.utcnow,
        sa_column=Column("created_at", DateTime, nullable=False),
    )
    status: str = Field(
        sa_column=Column("status", String, nullable=False, default="pending")
    )
    provider_ref: Optional[str] = Field(
        default=None, sa_column=Column("provider_ref", String)
    )

    __table_args__ = (
        UniqueConstraint("idempotency_key", "bank_id", name="credit_repay_idem_uniq"),
        Index("ix_credit_repay_bank_ts", "bank_id", "created_at"),
        {"extend_existing": True},
    )


class ProviderStatus(SQLModel, table=True):
    """Tracks provider adapter availability / quota."""

    id: Optional[int] = Field(default=None, primary_key=True)
    provider: str = Field(sa_column=Column("provider", String, nullable=False))
    last_success: Optional[datetime] = Field(
        default=None, sa_column=Column("last_success", DateTime)
    )
    last_error: Optional[datetime] = Field(
        default=None, sa_column=Column("last_error", DateTime)
    )
    message: Optional[str] = Field(default=None, sa_column=Column("message", String))

    __table_args__ = (UniqueConstraint("provider", name="provider_status_uniq"),)
