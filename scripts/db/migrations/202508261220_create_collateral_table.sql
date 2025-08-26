-- Create collateral_record table (Finastra Sprint-11)
CREATE TABLE IF NOT EXISTS collateralrecord (
    id TEXT PRIMARY KEY,
    bank_id TEXT,
    kind TEXT,
    status TEXT,
    currency TEXT,
    amount NUMERIC(18,2),
    valuation_ts TIMESTAMP,
    external_updated_ts TIMESTAMP,
    raw JSON NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Unique constraint across bank_id + id (multitenant safety)
CREATE UNIQUE INDEX IF NOT EXISTS collateral_bank_id_uniq ON collateralrecord (bank_id, id);

-- Index for incremental sync comparisons
CREATE INDEX IF NOT EXISTS ix_collateral_external_updated ON collateralrecord (external_updated_ts);
