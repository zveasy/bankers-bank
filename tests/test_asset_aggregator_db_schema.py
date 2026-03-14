from __future__ import annotations

from asset_aggregator.db import AssetSnapshot


def test_assetsnapshot_has_bank_ts_unique_constraint():
    unique_constraints = {
        tuple(c.columns.keys())
        for c in AssetSnapshot.__table__.constraints
        if c.__class__.__name__ == "UniqueConstraint"
    }
    assert ("bank_id", "ts") in unique_constraints
