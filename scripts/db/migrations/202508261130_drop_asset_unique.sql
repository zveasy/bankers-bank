-- Drop the UNIQUE CONSTRAINT on (bank_id, ts) in Postgres
-- Safe to run multiple times (IF EXISTS)
ALTER TABLE IF EXISTS assetsnapshot
    DROP CONSTRAINT IF EXISTS asset_snapshots_uniq;

-- Ensure a non-unique btree index remains for fast look-ups
CREATE INDEX IF NOT EXISTS ix_asset_snapshots_bank_ts
    ON assetsnapshot (bank_id, ts);
