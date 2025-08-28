/* Migration: create account_transactions table for Finastra Account Information US */

CREATE TABLE IF NOT EXISTS fin_account_transactions (
  id               INTEGER PRIMARY KEY,
  provider         TEXT NOT NULL,
  account_external_id TEXT NOT NULL,
  external_tx_id   TEXT NOT NULL,
  booking_date     TIMESTAMP NOT NULL,
  value_date       TIMESTAMP NULL,
  direction        TEXT NOT NULL,
  status           TEXT NULL,
  amount           NUMERIC(20,4) NOT NULL,
  currency         TEXT NOT NULL,
  description      TEXT NULL,
  reference        TEXT NULL,
  counterparty_name   TEXT NULL,
  counterparty_account TEXT NULL,
  scheme           TEXT NULL,
  category         TEXT NULL,
  fx_rate          NUMERIC(20,10) NULL,
  fx_src_ccy       TEXT NULL,
  fx_dst_ccy       TEXT NULL,
  fx_dst_amount    NUMERIC(20,4) NULL,
  source_hash      TEXT NOT NULL,
  raw_json         JSON,
  inserted_ts      TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
  last_seen_ts     TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE UNIQUE INDEX IF NOT EXISTS uq_tx_provider_acct_extid_booking
  ON fin_account_transactions(provider, account_external_id, external_tx_id, booking_date);

CREATE INDEX IF NOT EXISTS ix_tx_acct_booking
  ON fin_account_transactions(account_external_id, booking_date);

CREATE INDEX IF NOT EXISTS ix_tx_last_seen
  ON fin_account_transactions(last_seen_ts);
