import os
import subprocess
import sys
import tempfile
from pathlib import Path


import pytest
from sqlalchemy import create_engine, text



CLI_PATH = Path(__file__).resolve().parents[1] / "bin" / "audit-export"


@pytest.fixture()
def tmp_sqlite_db(tmp_path):
    db_path = tmp_path / "test.db"
    engine = create_engine(f"sqlite:///{db_path}")
    # create minimal audit table schema and seed one row
    with engine.begin() as conn:
        conn.execute(text("""
            CREATE TABLE credit_audit_journal (
              id TEXT PRIMARY KEY,
              created_at TEXT,
              event_ts TEXT,
              exported_at TEXT,
              export_file TEXT,
              export_id TEXT,
              bank_id TEXT,
              action TEXT,
              entity_type TEXT,
              entity_id TEXT,
              actor TEXT,
              payload TEXT,
              error_code TEXT,
              error_class TEXT,
              error_msg TEXT
            );
        """))
        conn.execute(text("INSERT INTO credit_audit_journal (id, created_at, event_ts, action, entity_type, entity_id, actor, payload, bank_id) VALUES ('row1', '2025-01-01', '2025-01-01', 'create', 't', '1', 'tester', '{}', 'bank1');"))
    return str(db_path)


def test_cli_runs(tmp_sqlite_db, tmp_path):
    # Load CLI as module
    # Run CLI in a separate subprocess to avoid module re-import side-effects
    out_dir = tmp_path / "out"
    os.makedirs(out_dir)

    cmd = [sys.executable, str(CLI_PATH), "--db-url", f"sqlite:///{tmp_sqlite_db}", "--out-dir", str(out_dir), "--batch-size", "100"]
    result = subprocess.run(cmd, check=True, capture_output=True, text=True)
    assert result.returncode == 0

    files = list(out_dir.glob("*.ndjson.gz"))
    assert files, "CLI did not write any export file"
