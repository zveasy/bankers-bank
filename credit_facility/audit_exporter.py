# credit_facility/audit_exporter.py
"""Audit exporter for credit_facility service."""
from __future__ import annotations

import gzip
import json
import os
import socket
import tempfile
import time
from datetime import date, datetime, time as dtime, timedelta, timezone
from pathlib import Path
from typing import Any, List

import ulid
from dateutil.parser import isoparse  # <-- robust ISO8601 parser
from sqlalchemy import func, select, text
from sqlmodel import Session

from treasury_orchestrator.credit_db import AuditJournal
from treasury_observability import metrics as met

HOSTNAME = socket.gethostname()

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

def _now_utc_iso_z() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")

def _atomic_write_gz_ndjson(lines: List[str], export_id: str, directory: Path = EXPORT_DIR) -> Path:
    ts_safe = datetime.utcnow().strftime("%Y%m%dT%H%M%SZ")  # Windows-safe (no ':')
    fname = f"audit-{ts_safe}-{HOSTNAME}-{os.getpid()}-{export_id}.ndjson.gz"
    directory.mkdir(parents=True, exist_ok=True)

    tmp_fd, tmp_path = tempfile.mkstemp(dir=directory, suffix=".tmp")
    path_tmp = Path(tmp_path)
    try:
        with gzip.GzipFile(fileobj=os.fdopen(tmp_fd, "wb"), mode="w", mtime=0) as gz:
            for line in lines:
                gz.write(line.encode("utf-8"))
                gz.write(b"\n")
        try:
            with path_tmp.open("rb+") as f:
                os.fsync(f.fileno())
        except OSError:
            pass
        final_path = directory / fname
        path_tmp.rename(final_path)
        try:
            os.chmod(final_path, 0o640)
        except OSError:
            pass
        return final_path
    except Exception:
        path_tmp.unlink(missing_ok=True)
        raise

def _sanitize_payload(payload: dict | None) -> dict:
    if not payload:
        return {}
    out: dict[str, Any] = {}
    for k, v in payload.items():
        if isinstance(v, str) and v.isdigit() and len(v) >= 8:
            out[k] = f"***{v[-4:]}"
        else:
            out[k] = v
    return out

def _coerce_ts(v: Any) -> str | None:
    """
    Normalize timestamps to RFC3339 'Z'.
    Accepts datetime/date/epoch/ISO strings (incl. 'YYYY-MM-DD').
    """
    if v is None:
        return None
    if isinstance(v, datetime):
        dt = v if v.tzinfo else v.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")
    if isinstance(v, date) and not isinstance(v, datetime):
        dt = datetime.combine(v, dtime.min, tzinfo=timezone.utc)
        return dt.isoformat().replace("+00:00", "Z")
    if isinstance(v, (int, float)):
        dt = datetime.fromtimestamp(v, tz=timezone.utc)
        return dt.isoformat().replace("+00:00", "Z")
    if isinstance(v, str):
        # isoparse handles date-only; add UTC if naive
        dt = isoparse(v)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")
    return str(v)

class AuditExporter:
    """Batch exporter for `AuditJournal`."""

    def __init__(self, session_factory, *, batch_size: int = BATCH_SIZE, cutoff_seconds: int = CUTOFF_SEC, out_dir: Path = EXPORT_DIR):
        self._session_factory = session_factory
        self.batch_size = batch_size
        self.cutoff = cutoff_seconds
        self.out_dir = out_dir

    def run_until_empty(self, *, now: datetime | None = None, max_batches: int | None = None, dry_run: bool = False) -> dict:
        batches = 0
        last: dict | None = None
        while True:
            if max_batches is not None and batches >= max_batches:
                break
            stats = self._export_one_batch(now=now, dry_run=dry_run)
            last = stats
            if stats["selected"] == 0:
                break
            batches += 1
        return last or {"selected": 0, "written": 0, "file": None, "export_id": ""}

    def _export_one_batch(self, *, now: datetime | None = None, dry_run: bool = False) -> dict:
        t0 = time.perf_counter()
        selected = written = 0
        export_id = ""
        file_path: Path | None = None

        with self._session_factory() as sess:
            rows = self._select_rows(sess)
            selected = len(rows)
            if not rows:
                self._update_backlog_gauge(sess)
                return {"selected": 0, "written": 0, "file": None, "export_id": ""}

            export_id = str(ulid.new())
            header = json.dumps({"_type": "audit_export", "_v": 1, "export_id": export_id, "created_at": _now_utc_iso_z()})
            ndjson_lines = [header]
            for r in rows:
                payload = _sanitize_payload(getattr(r, "payload", None))
                ndjson_lines.append(
                    json.dumps(
                        {
                            "_v": 1,
                            "export_id": export_id,
                            "journal_id": r.id,
                            "ts": _coerce_ts(getattr(r, "event_ts", None)),
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
                if not dry_run:
                    file_path = _atomic_write_gz_ndjson(ndjson_lines, export_id, self.out_dir)
                written = len(rows)
                now_utc = (now or datetime.utcnow()).replace(tzinfo=timezone.utc)
                for r in rows:
                    r.exported_at = now_utc
                    r.export_file = file_path.name if file_path else None
                    r.export_id = export_id
                sess.commit()
                met.audit_export_files_written_total.labels(service=SERVICE_NAME, result="success").inc()
            except Exception:
                sess.rollback()
                met.audit_export_files_written_total.labels(service=SERVICE_NAME, result="fail").inc()
                raise
            finally:
                met.audit_export_duration_seconds.labels(service=SERVICE_NAME).observe(time.perf_counter() - t0)
                met.audit_export_rows_selected_total.labels(service=SERVICE_NAME).inc(selected)
                self._update_backlog_gauge(sess)

        return {"selected": selected, "written": written, "file": str(file_path) if (file_path and not dry_run) else None, "export_id": export_id}

    def export_once(self) -> dict:
        return self._export_one_batch()

    def retention_sweep(self, older_than_days: int | None = None) -> int:
        days = older_than_days or RETENTION_DAYS
        cutoff = datetime.utcnow() - timedelta(days=days)
        with self._session_factory() as sess:
            n = sess.exec(
                select(func.count())
                .select_from(AuditJournal)
                .where(AuditJournal.exported_at.is_not(None), AuditJournal.exported_at < cutoff)
            ).scalar()
            sess.execute(text("DELETE FROM credit_audit_journal WHERE exported_at IS NOT NULL"))
            sess.commit()
            met.audit_retention_rows_deleted_total.labels(service=SERVICE_NAME).inc(n)
            return n

    def _select_rows(self, sess: Session):
        stmt = (
            select(AuditJournal)
            .where(AuditJournal.exported_at.is_(None))
            .order_by(AuditJournal.event_ts)
        )
        if self.cutoff > 0:
            cutoff_ts = datetime.utcnow() - timedelta(seconds=self.cutoff)
            stmt = stmt.where(AuditJournal.event_ts <= cutoff_ts)
        stmt = stmt.limit(self.batch_size).with_for_update(skip_locked=True)
        return sess.exec(stmt).scalars().all()

    def _update_backlog_gauge(self, sess: Session):
        cutoff_ts = datetime.utcnow() - timedelta(seconds=self.cutoff)
        backlog = sess.exec(
            select(func.count())
            .select_from(AuditJournal)
            .where(AuditJournal.exported_at.is_(None), AuditJournal.event_ts <= cutoff_ts)
        ).scalar()
        met.audit_backlog_rows.labels(service=SERVICE_NAME).set(backlog)
