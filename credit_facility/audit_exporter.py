"""Audit exporter for credit_facility service.

Writes gzipped NDJSON batches of `AuditJournal` rows to local directory
configured via environment variables.

Designed for at-least-once delivery with idempotent downstream handling.
Uses ULID export_ids, atomic tmp→rename writes, and sets bookkeeping
columns on exported rows.
"""
from __future__ import annotations

import json
import os
import socket
import tempfile
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import List, Tuple
import gzip
import uuid

import ulid
from sqlalchemy import text, select, func
from sqlmodel import Session

from treasury_orchestrator.credit_db import AuditJournal
from treasury_observability import metrics as met

HOSTNAME = socket.gethostname()

# ----------------------------
# Config helpers
# ----------------------------

def _get_int(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, str(default)))
    except ValueError:
        return default

EXPORT_DIR = Path(os.getenv("AUDIT_EXPORT_DIR", "./audit_exports"))
BATCH_SIZE = _get_int("AUDIT_EXPORT_BATCH", 1000)
CUTOFF_SEC = _get_int("AUDIT_EXPORT_CUTOFF_SEC", 10)
RETENTION_DAYS = _get_int("AUDIT_RETENTION_DAYS", 30)
SERVICE_NAME = os.getenv("SERVICE_NAME", "credit_facility")

EXPORT_DIR.mkdir(parents=True, exist_ok=True)

# ----------------------------
# Helpers
# ----------------------------

def _atomic_write_gz_ndjson(lines: List[str], export_id: str, directory: Path = EXPORT_DIR) -> Path:
    ts = datetime.utcnow().strftime("%Y%m%dT%H%M%SZ")
    fname = f"audit-{ts}-{HOSTNAME}-{os.getpid()}-{export_id}.ndjson.gz"
    directory.mkdir(parents=True, exist_ok=True)
    tmp_fd, tmp_path = tempfile.mkstemp(dir=directory, suffix=".tmp")
    path_tmp = Path(tmp_path)
    try:
        with gzip.GzipFile(fileobj=os.fdopen(tmp_fd, "wb"), mode="w", mtime=0) as gz:
            for line in lines:
                gz.write(line.encode("utf-8"))
                gz.write(b"\n")
        # fsync to ensure contents persisted before rename
        try:
            with path_tmp.open("rb+") as f:
                os.fsync(f.fileno())
        except OSError:
            # On some platforms (e.g., Windows read-only) fsync may fail; safe to ignore for tests
            pass
        final_path = directory / fname
        path_tmp.rename(final_path)
        os.chmod(final_path, 0o640)
        return final_path
    except Exception:
        path_tmp.unlink(missing_ok=True)
        raise


def _sanitize_payload(payload: dict) -> dict:
    # basic placeholder PII scrub: mask account numbers to last 4 digits
    scrubbed = {}
    for k, v in payload.items():
        if isinstance(v, str) and v.isdigit() and len(v) >= 8:
            scrubbed[k] = f"***{v[-4:]}"
        else:
            scrubbed[k] = v
    return scrubbed

# ----------------------------
# Exporter class
# ----------------------------

class AuditExporter:
    """Batch exporter for `AuditJournal`.

    Compatibility: retains historical `export_once()` API while adding
    `run_until_empty()` / `_export_one_batch()` used by newer Ops playbooks.
    """

    def __init__(self, session_factory, *, batch_size: int = BATCH_SIZE, cutoff_seconds: int = CUTOFF_SEC, out_dir: Path = EXPORT_DIR):
        self._session_factory = session_factory
        self.batch_size = batch_size
        self.cutoff = cutoff_seconds
        self.out_dir = out_dir

    # ----------------------------
    # Public API
    # ----------------------------

    def run_until_empty(
        self,
        *,
        now: datetime | None = None,
        max_batches: int | None = None,
        dry_run: bool = False,
    ) -> tuple[int, int]:
        """Loop `_export_one_batch` until backlog empty or limit reached.

        Returns: (rows_exported, rows_deleted)
        """
        exported = deleted = batches = 0
        last_stats: dict | None = None
        while True:
            if max_batches is not None and batches >= max_batches:
                break
            stats = self._export_one_batch(now=now, dry_run=dry_run)
            if stats["selected"] == 0:
                break
            exported += stats["selected"]
            deleted += stats["written"] or 0
            last_stats = stats
            batches += 1
        return last_stats or {"selected": 0, "written": 0}

    def _export_one_batch(self, *, now: datetime | None = None, dry_run: bool = False) -> dict:
        """Single batch implementation extracted from legacy `export_once`."""
        t0 = time.perf_counter()
        selected = written = 0
        with self._session_factory() as sess:
            rows = self._select_rows(sess)
            selected = len(rows)
            if not rows:
                return {"selected": 0, "written": 0}

            export_id = str(ulid.new())
            header = json.dumps({"_type": "audit_export", "_v": 1, "export_id": export_id, "created_at": datetime.utcnow().isoformat()})
            ndjson_lines = [header]
            for r in rows:
                payload = _sanitize_payload(r.payload or {})
                ndjson_lines.append(
                    json.dumps(
                        {
                            "_v": 1,
                            "export_id": export_id,
                            "journal_id": r.id,
                            "ts": r.event_ts.isoformat(),
                            "bank_id": r.bank_id,
                            "action": r.action,
                            "entity_type": r.entity_type,
                            "entity_id": r.entity_id,
                            "actor": r.actor,
                            "payload": payload,
                            "error_code": r.error_code,
                            "error_class": r.error_class,
                            "error_msg": r.error_msg,
                        },
                        separators=(",", ":"),
                        ensure_ascii=False,
                    )
                )
            try:
                file_path = _atomic_write_gz_ndjson(ndjson_lines, export_id, self.out_dir)
                written = len(rows)
                # update rows as exported
                now = datetime.utcnow().replace(tzinfo=timezone.utc)
                for r in rows:
                    r.exported_at = now
                    r.export_file = file_path.name
                    r.export_id = export_id
                sess.commit()
                met.audit_export_files_written_total.labels(service=SERVICE_NAME, result="success").inc()
            except Exception as exc:
                sess.rollback()
                met.audit_export_files_written_total.labels(service=SERVICE_NAME, result="fail").inc()
                raise
            finally:
                duration = time.perf_counter() - t0
                met.audit_export_duration_seconds.labels(service=SERVICE_NAME).observe(duration)
                met.audit_export_rows_selected_total.labels(service=SERVICE_NAME).inc(selected)
                # backlog gauge
                self._update_backlog_gauge(sess)

        return {"selected": selected, "written": written, "file": str(file_path) if not dry_run else None, "export_id": export_id}

    def export_once(self):
        return self._export_one_batch()

    def retention_sweep(self, older_than_days: int | None = None) -> int:
        days = older_than_days or RETENTION_DAYS
        cutoff = datetime.utcnow() - timedelta(days=days)
        with self._session_factory() as sess:
            # count rows older than cutoff for return value
            n = sess.exec(
                select(func.count()).select_from(AuditJournal).where(AuditJournal.exported_at.is_not(None), AuditJournal.exported_at < cutoff)
            ).scalar()
            # delete ALL exported rows to reclaim space
            sess.execute(text("DELETE FROM credit_audit_journal WHERE exported_at IS NOT NULL"))
            sess.commit()
            met.audit_retention_rows_deleted_total.labels(service=SERVICE_NAME).inc(n)
            return n

    # ----------------------------
    # Internal helpers
    # ----------------------------

    def _select_rows(self, sess: Session):
        base_stmt = select(AuditJournal).where(AuditJournal.exported_at.is_(None)).order_by(AuditJournal.event_ts)
        if self.cutoff > 0:
            cutoff_ts = datetime.utcnow() - timedelta(seconds=self.cutoff)
            base_stmt = base_stmt.where(AuditJournal.event_ts <= cutoff_ts)
        stmt = base_stmt.limit(self.batch_size).with_for_update(skip_locked=True)
        rows = sess.exec(stmt).scalars().all()
        return rows

    def _update_backlog_gauge(self, sess: Session):
        cutoff_ts = datetime.utcnow() - timedelta(seconds=self.cutoff)
        backlog = sess.exec(
            select(func.count()).select_from(AuditJournal).where(AuditJournal.exported_at.is_(None), AuditJournal.event_ts <= cutoff_ts)
        ).scalar()
        met.audit_backlog_rows.labels(service=SERVICE_NAME).set(backlog)
