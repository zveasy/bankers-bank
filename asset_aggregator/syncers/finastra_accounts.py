from __future__ import annotations

"""Sync Finastra accounts into `AccountRecord`.
Offline-safe, idempotent (external_updated_ts + source_hash), Prom metrics.
"""

import hashlib
import json
import os
from datetime import timezone
from common.datetime import parse_iso8601
from typing import Callable, List

from prometheus_client import Counter, Gauge
from sqlmodel import Session, SQLModel, create_engine, select

from integrations.finastra.accounts_client import AccountsClient, Account
from treasury_domain.account_models import AccountRecord

DB_URL = os.getenv("ASSET_DB_URL", "sqlite:///./asset_aggregator.db")
engine = create_engine(DB_URL, echo=False)
SQLModel.metadata.create_all(engine)

# Metrics
_ACC_UPSERT_TOTAL = Counter(
    "accounts_upsert_total", "Account rows processed", labelnames=["result"]
)
_ACC_LAST_SUCCESS = Gauge(
    "accounts_last_success_unixtime", "Unix timestamp of last successful accounts sync"
)


# Helpers ----------------------------------------------------------------

def _calc_hash(src: dict) -> str:
    blob = json.dumps(src, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(blob).hexdigest()


def _should_update(incoming: Account, existing: AccountRecord, new_hash: str) -> bool:
    if incoming.updated:
        try:
            inc_ts = parse_iso8601(incoming.updated).replace(tzinfo=None)
        except ValueError:
            inc_ts = None
    else:
        inc_ts = None
    if inc_ts and existing.external_updated_ts and inc_ts > existing.external_updated_ts:
        return True
    if existing.source_hash != new_hash:
        return True
    return False


# Upsert ------------------------------------------------------------------

def _upsert_batch(sess: Session, rows: List[Account]):
    created = updated = skipped = 0
    for acc in rows:
        hsh = _calc_hash(acc.raw)
        existing = sess.exec(
            select(AccountRecord).where(
                AccountRecord.provider == "finastra",
                AccountRecord.external_id == acc.external_id,
            )
        ).first()
        if existing:
            if _should_update(acc, existing, hsh):
                existing.account_number = acc.raw.get("accountNumber")
                existing.iban = acc.raw.get("iban")
                existing.currency = acc.currency
                existing.context = acc.context
                existing.type = acc.type
                existing.status = acc.status
                existing.external_updated_ts = (
                    parse_iso8601(acc.updated).replace(tzinfo=None)
                    if acc.updated
                    else None
                )
                existing.source_hash = hsh
                updated += 1
            else:
                skipped += 1
        else:
            sess.add(
                AccountRecord(
                    provider="finastra",
                    external_id=acc.external_id,
                    account_number=acc.raw.get("accountNumber"),
                    iban=acc.raw.get("iban"),
                    currency=acc.currency,
                    context=acc.context,
                    type=acc.type,
                    status=acc.status,
                    external_updated_ts=(
                        parse_iso8601(acc.updated).replace(tzinfo=None)
                        if acc.updated
                        else None
                    ),
                    source_hash=hsh,
                )
            )
            created += 1
    sess.commit()
    for lbl, val in {"created": created, "updated": updated, "skipped": skipped}.items():
        if val:
            _ACC_UPSERT_TOTAL.labels(result=lbl).inc(val)


# Syncer ------------------------------------------------------------------

class FinastraAccountsSyncer:
    def __init__(self, *, client: AccountsClient, session_factory: Callable[[], Session]):
        self._client = client
        self._session_factory = session_factory

    async def run_once(self, contexts: list[str] | None = None) -> int:
        contexts = contexts or ["MT103", "INTERNAL-TRANSFER"]
        processed = 0
        for ctx in contexts:
            async for page in self._client.list_accounts(ctx):
                with self._session_factory() as sess:
                    _upsert_batch(sess, page)
                processed += len(page)
        _ACC_LAST_SUCCESS.set_to_current_time()
        return processed
