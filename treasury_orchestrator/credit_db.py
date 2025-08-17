import os
from enum import Enum
from uuid import uuid4
import ulid
from datetime import datetime
from typing import Optional, Any, Dict

from sqlmodel import Field, Session, SQLModel, create_engine
from sqlalchemy import Column
from sqlalchemy.types import JSON as SA_JSON
from sqlalchemy.dialects.postgresql import JSONB

DATABASE_URL = os.getenv("CREDIT_DB_URL", "sqlite:///./credit_facility.db")
engine = create_engine(DATABASE_URL, echo=False)


class CreditFacility(SQLModel, table=True):
    """Credit facility master record."""

    __table_args__ = {"extend_existing": True}

    id: str = Field(primary_key=True)
    bank_id: str = Field(default="test")
    currency: str = Field(default="USD")
    cap: float = 0.0
    buffer: float = 0.0
    limit: float
    drawn: float = 0.0
    ltv_limit: float
    updated_at: datetime = Field(default_factory=datetime.utcnow)


# ---------------------------------------------------------------------------
# Existing models
# ---------------------------------------------------------------------------

class CreditTxn(SQLModel, table=True):
    """Individual credit facility transactions."""

    __table_args__ = {"extend_existing": True}

    id: Optional[int] = Field(default=None, primary_key=True)
    facility_id: str = Field(foreign_key="creditfacility.id")
    amount: float
    txn_type: str
    ts: datetime = Field(default_factory=datetime.utcnow)


# ---------------------------------------------------------------------------
# Audit / retention additions
# ---------------------------------------------------------------------------

class AuditAction(str, Enum):
    DRAW_CREATED = "draw_created"
    REPAY_CREATED = "repay_created"
    STATUS_UPDATED = "status_updated"

# portable JSON column across SQLite / Postgres
JSON_PORTABLE = Field(sa_column=SA_JSON().with_variant(JSONB, "postgresql"))

class AuditJournal(SQLModel, table=True):
    __tablename__ = "credit_audit_journal"

    id: str = Field(primary_key=True, default_factory=lambda: str(ulid.new()))
    event_ts: datetime = Field(default_factory=datetime.utcnow, index=True)
    actor: str = Field(default="system", index=True)
    action: str = Field(index=True)
    entity_type: str = Field(index=True)
    entity_id: str = Field(index=True)
    bank_id: Optional[str] = Field(default=None, index=True)
    payload: Optional[dict] = Field(default=None, sa_column=Column(SA_JSON().with_variant(JSONB, "postgresql")))
    # bookkeeping for exporter
    exported_at: Optional[datetime] = Field(default=None, index=True)
    export_file: Optional[str] = None
    export_id: Optional[str] = None
    # error normalization
    error_code: Optional[str] = None
    error_class: Optional[str] = None
    error_msg: Optional[str] = None


def log_audit(
    session: Session,
    *,
    action: AuditAction,
    entity_type: str,
    entity_id: str,
    bank_id: Optional[str] = None,
    actor: str = "system",
    payload: dict | None = None,
) -> None:
    """Persist immutable audit row."""
    row = AuditJournal(
        action=action.value,
        entity_type=entity_type,
        entity_id=entity_id,
        bank_id=bank_id,
        actor=actor,
        payload=payload or {},
        error_code=None,
        error_class=None,
        error_msg=None,
    )
    session.add(row)
    # don't commit; caller responsible to maintain transaction atomicity

# ---------------------------------------------------------------------------
# Utilities
# ---------------------------------------------------------------------------

def init_db() -> None:
    SQLModel.metadata.create_all(engine)


def get_session() -> Session:
    return Session(engine)
