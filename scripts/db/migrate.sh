#!/bin/sh
set -e

# Run Python-based migrations (SQLModel create_all)
python - <<'PY'
from common import audit

# This will create the audit_journal table if it does not exist (both SQLite & Postgres)
audit.SQLModel.metadata.create_all(audit.get_engine())
print("audit_journal ensured")
PY

