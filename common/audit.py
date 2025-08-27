from __future__ import annotations

"""Shared audit logging utilities.

All services append immutable rows to the ``audit_journal`` table, enabling a
central exporter to back up or stream audit events for compliance.
"""

import os
from datetime import datetime
from typing import Any, Dict, Optional

from sqlalchemy import JSON, Column, String, create_engine
from sqlmodel import Field, SQLModel, Session

__all__ = [
    "AuditJournal",
    "get_engine",
    "get_session",
    "log_event",
]


# ---------------------------------------------------------------------------
# Database setup
# ---------------------------------------------------------------------------


AUDIT_DB_URL = os.getenv("AUDIT_DB_URL", "sqlite:///./.data/audit_journal.db")

engine = create_engine(
    AUDIT_DB_URL,
    echo=False,
    connect_args={"check_same_thread": False} if AUDIT_DB_URL.startswith("sqlite") else {},
)


class AuditJournal(SQLModel, table=True):
    """Immutable audit log for cross-service compliance."""

    id: Optional[int] = Field(default=None, primary_key=True)

    # RFC3339 timestamp (UTC) when the action occurred.
    ts: datetime = Field(default_factory=datetime.utcnow, index=True)

    # Name of the micro-service emitting the event e.g. "credit_facility"
    service: str = Field(sa_column=Column(String, nullable=False, index=True))

    # Authenticated user / system actor, free-form string (email, role, etc.)
    actor: Optional[str] = None

    # Action verb e.g. "CREATE_COLLATERAL", "APPROVE_SWEEP_ORDER"
    action: str = Field(sa_column=Column(String, nullable=False))

    # JSON payload with additional structured context (schema per action)
    details: Dict[str, Any] = Field(
        default_factory=dict, sa_column=Column(JSON, nullable=False, default={})
    )


# Idempotent table creation for local dev and during tests.
SQLModel.metadata.create_all(engine)


# ---------------------------------------------------------------------------
# Helper functions
# ---------------------------------------------------------------------------

def get_engine():
    """Return the shared audit engine (for migrations / scripting)."""

    return engine


def get_session():
    """Context-managed session generator (FastAPI dependency style)."""

    with Session(engine) as session:
        yield session


def log_event(
    *,
    session: Session,
    service: str,
    action: str,
    actor: Optional[str] = None,
    details: Optional[Dict[str, Any]] = None,
) -> None:
    """Insert a new audit record and commit immediately.

    Parameters
    ----------
    session: SQLModel Session bound to *any* service DB. We attach the audit
        engine via cross-database session.merge(); this avoids each service
        having to keep two engines open simultaneously.
    service: Name of the emitting micro-service.
    action: Action verb.
    actor: Who performed the action.
    details: JSON-serialisable dictionary with extra context.
    """

    entry = AuditJournal(
        service=service,
        action=action,
        actor=actor,
        details=details or {},
    )

    # Use separate engine – add through new Session to avoid mixing transactions.
    with Session(engine) as audit_sess:
        audit_sess.add(entry)
        audit_sess.commit()
