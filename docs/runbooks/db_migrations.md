# DB Migrations (Alembic)

This repository now includes Alembic scaffolding for schema migrations.

## Commands

```bash
# apply all migrations
make db-migrate

# rollback one revision
make db-downgrade

# generate a new migration (example message)
make db-revision m="add new column to fin_accounts"
```

## Configuration

- Alembic config: `alembic.ini`
- Migration environment: `alembic/env.py`
- Revisions: `alembic/versions/`

Alembic reads the target database URL from `ASSET_DB_URL` (falling back to the
URL in `alembic.ini`).
