#!/usr/bin/env python3
"""Re-ingest NDJSON audit exports back into the credit_audit_journal table.

Idempotent: skips rows whose ULID already exists.

Usage:
    python scripts/restore_audit_from_ndjson.py --db-url postgresql://... export1.ndjson.gz export2.ndjson.gz
"""
from __future__ import annotations

import argparse
import gzip
import json
import sys
from pathlib import Path
from typing import Iterable, List

from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session

HEADER_TYPE = "audit_export"


def parse_args() -> argparse.Namespace:
    ap = argparse.ArgumentParser(description="Restore audit journal rows from NDJSON exports")
    ap.add_argument("--db-url", required=True, help="SQLAlchemy database URL")
    ap.add_argument("files", nargs="+", help="NDJSON(.gz) files to restore")
    return ap.parse_args()


def read_ndjson(path: Path) -> Iterable[dict]:
    opener = gzip.open if path.suffix == ".gz" else open  # type: ignore[arg-type]
    with opener(path, "rt") as fh:
        for i, line in enumerate(fh):
            if i == 0:  # header line
                hdr = json.loads(line)
                if hdr.get("_type") != HEADER_TYPE:
                    raise ValueError(f"{path} is not an audit_export file")
                continue
            yield json.loads(line)


def ingest(engine, rows: List[dict]):
    if not rows:
        return 0
    with engine.begin() as conn:
        # create temp table for bulk insert then merge
        conn.execute(text("""
            CREATE TEMP TABLE _import_journal (
                id TEXT PRIMARY KEY,
                created_at TIMESTAMPTZ,
                event_ts TIMESTAMPTZ,
                action TEXT,
                entity_type TEXT,
                entity_id TEXT,
                actor TEXT,
                payload JSONB,
                error_code TEXT,
                error_class TEXT,
                error_msg TEXT
            ) ON COMMIT DROP;
        """))
        for row in rows:
            conn.execute(
                text("INSERT INTO _import_journal VALUES (:id,:created_at,:event_ts,:action,:entity_type,:entity_id,:actor,:payload::jsonb,:error_code,:error_class,:error_msg)"),
                row,
            )
        result = conn.execute(
            text(
                """
                INSERT INTO credit_audit_journal (id, created_at, event_ts, action, entity_type, entity_id, actor, payload, error_code, error_class, error_msg)
                SELECT id, created_at, event_ts, action, entity_type, entity_id, actor, payload, error_code, error_class, error_msg
                FROM _import_journal i
                WHERE NOT EXISTS (SELECT 1 FROM credit_audit_journal j WHERE j.id = i.id);
                """
            )
        )
        return result.rowcount


def main():
    args = parse_args()
    engine = create_engine(args.db_url, future=True)
    total = 0
    for f in args.files:
        path = Path(f)
        rows = list(read_ndjson(path))
        inserted = ingest(engine, rows)
        print(f"{path}: inserted {inserted} rows")
        total += inserted
    print(f"Total inserted: {total}")


if __name__ == "__main__":
    sys.exit(main())
