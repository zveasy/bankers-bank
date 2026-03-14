"""ensure assetsnapshot uniqueness for upsert conflict target

Revision ID: 20260314_0001
Revises:
Create Date: 2026-03-14 00:00:00
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "20260314_0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    tables = set(inspector.get_table_names())
    if "assetsnapshot" not in tables:
        return

    existing_uniques = {u.get("name") for u in inspector.get_unique_constraints("assetsnapshot")}
    existing_indexes = {i.get("name") for i in inspector.get_indexes("assetsnapshot")}

    if "assetsnapshot_bank_ts_uniq" not in existing_uniques and "assetsnapshot_bank_ts_uniq" not in existing_indexes:
        with op.batch_alter_table("assetsnapshot") as batch_op:
            batch_op.create_unique_constraint(
                "assetsnapshot_bank_ts_uniq",
                ["bank_id", "ts"],
            )


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    tables = set(inspector.get_table_names())
    if "assetsnapshot" not in tables:
        return

    existing_uniques = {u.get("name") for u in inspector.get_unique_constraints("assetsnapshot")}
    if "assetsnapshot_bank_ts_uniq" in existing_uniques:
        with op.batch_alter_table("assetsnapshot") as batch_op:
            batch_op.drop_constraint("assetsnapshot_bank_ts_uniq", type_="unique")
