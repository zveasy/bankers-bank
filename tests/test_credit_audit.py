"""Unit tests for credit audit exporter and journal emission."""
from __future__ import annotations

import gzip
import json
import os
from datetime import datetime, timedelta
from pathlib import Path
from typing import List

import pytest
from sqlmodel import Session, select

import sqlalchemy
from sqlmodel import SQLModel, create_engine

# Use dedicated in-memory SQLite engine for this module only
_test_engine = create_engine("sqlite:///:memory:", echo=False)

def _setup_test_db():
    # Rebind credit_db.engine to isolated engine
    from treasury_orchestrator import credit_db as _db
    _db.engine = _test_engine  # type: ignore
    SQLModel.metadata.create_all(_test_engine)

_setup_test_db()

# Configure exporter env
os.environ["AUDIT_EXPORT_DIR"] = "/tmp/audit_test"

from treasury_orchestrator.credit_db import (  # noqa: E402  (after env override)
    AuditAction,
    AuditJournal,
    get_session,
    init_db,
    log_audit,
)
from credit_facility.audit_exporter import AuditExporter, BATCH_SIZE

EXPORT_DIR = Path(os.getenv("AUDIT_EXPORT_DIR"))
EXPORT_DIR.mkdir(parents=True, exist_ok=True)


@pytest.fixture()
def session() -> Session:
    with Session(_test_engine) as s:
        yield s


@pytest.fixture()
def exporter() -> AuditExporter:
    from treasury_orchestrator import credit_db as _db
    return AuditExporter(lambda: Session(_test_engine), batch_size=10, cutoff_seconds=0)  # immediate export


def _seed_rows(n: int, *, session: Session, action: AuditAction = AuditAction.DRAW_CREATED):
    for i in range(n):
        log_audit(
            session,
            action=action,
            entity_type="credit_draw",
            entity_id=f"row{i}",
            bank_id="bankX",
            payload={"acct": "1234567890", "amount": 100},
        )
    session.commit()


def test_exporter_writes_file_and_updates_rows(exporter: AuditExporter, session: Session):
    _seed_rows(5, session=session)
    stats = exporter.export_once()
    assert stats["selected"] == 5 and stats["written"] == 5

    # Rows now have exported_at
    rows: List[AuditJournal] = session.exec(select(AuditJournal)).all()  # type: ignore
    assert all(r.exported_at for r in rows)

    # File exists and gzip integrity
    fpath = Path(stats["file"])
    assert fpath.exists()
    with gzip.open(fpath, "rt") as gf:
        lines = gf.read().strip().split("\n")
    assert len(lines) == 6  # header + 5 lines

    obj = json.loads(lines[1])
    # PII scrubbed acct
    assert obj["payload"]["acct"] == "***7890"


def test_batching_and_idempotency(exporter: AuditExporter, session: Session):
    # Seed > batch size rows
    _seed_rows(12, session=session)
    exporter.batch_size = 10
    first = exporter.export_once()
    assert first["written"] == 10
    second = exporter.export_once()
    # remaining 2 rows
    assert second["written"] == 2
    # re-run with no new rows
    third = exporter.export_once()
    assert third.get("selected", 0) == 0


def test_retention_sweep(exporter: AuditExporter, session: Session):
    # create row with exported_at 40 days ago
    _seed_rows(1, session=session)
    exporter.export_once()
    old_time = datetime.utcnow() - timedelta(days=40)
    row: AuditJournal = session.exec(select(AuditJournal)).first()  # type: ignore
    row.exported_at = old_time
    session.add(row)
    session.commit()

    deleted = exporter.retention_sweep(older_than_days=30)
    assert deleted == 1

    remaining = session.exec(select(AuditJournal)).all()  # type: ignore
    assert len(remaining) == 0
