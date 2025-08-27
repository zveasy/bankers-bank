-- Migration: create Finastra account & balance tables
-- Generated 2025-08-26 19:28 UTC

BEGIN;

-- Accounts -----------------------------------------------------------------
CREATE TABLE IF NOT EXISTS fin_accounts (
    id               INTEGER PRIMARY KEY AUTOINCREMENT,
    provider         TEXT NOT NULL DEFAULT 'finastra',
    external_id      TEXT NOT NULL,
    account_number   TEXT,
    iban             TEXT,
    currency         TEXT,
    context          TEXT,
    type             TEXT,
    status           TEXT,
    external_updated_ts TIMESTAMP WITH TIME ZONE,
    source_hash      CHAR(64),
    created_ts       TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP NOT NULL,
    updated_ts       TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP NOT NULL
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_accounts_provider_ext
    ON fin_accounts(provider, external_id);

-- Balances ------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS fin_balances (
    id               INTEGER PRIMARY KEY AUTOINCREMENT,
    provider         TEXT NOT NULL DEFAULT 'finastra',
    account_external_id TEXT NOT NULL,
    as_of_ts         TIMESTAMP WITH TIME ZONE NOT NULL,
    current_amount   NUMERIC(20,4) NOT NULL,
    available_amount NUMERIC(20,4),
    credit_limit_amount NUMERIC(20,4),
    currency         TEXT,
    source_hash      CHAR(64),
    created_ts       TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP NOT NULL,
    updated_ts       TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_balances_provider_acct_ts
    ON fin_balances(provider, account_external_id, as_of_ts);

COMMIT;
