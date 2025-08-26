from __future__ import annotations

"""Sync Finastra balances into `BalanceRecord`.
Offline-friendly, idempotent via `as_of_ts` + `source_hash` per account.
"""

import hashlib
import json
import os
from datetime import datetime, timezone
from typing import Callable, List, Optional

from prometheus_client import Counter, Gauge
from sqlmodel import Session, SQLModel, create_engine, select

from integrations.finastra.balances_client import BalancesClient, Balance
from treasury_domain.account_models import BalanceRecord, AccountRecord

DB_URL = os.getenv("ASSET_DB_URL", "sqlite:///./asset_aggregator.db")
engine = create_engine(DB_URL, echo=False)
SQLModel.metadata.create_all(engine)

_BAL_UPSERT_TOTAL = Counter(
    "balances_upsert_total", "Balance rows processed", labelnames=["result"]
)
_BAL_LAST_SUCCESS = Gauge(
    "balances_last_success_unixtime", "Unix timestamp of last successful balances sync"
)


# Helpers -----------------------------------------------------------------

def _calc_hash(src: dict) -> str:
    blob = json.dumps(src, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(blob).hexdigest()


def _parse_ts(val: str | None) -> Optional[datetime]:
    if not val:
        return None
    try:
        return (
            datetime.fromisoformat(val.replace("Z", "+00:00"))
            .astimezone(timezone.utc)
            .replace(tzinfo=None)
        )
    except ValueError:
        return None


# Upsert -------------------------------------------------------------------

def _upsert_batch(sess: Session, balances: List[Balance]):
    created = updated = skipped = 0
    for b in balances:
        hsh = _calc_hash(b)
        as_of = _parse_ts(b.as_of_ts)
        if as_of is None:
            # skip malformed row
            continue
        existing = sess.exec(
            select(BalanceRecord).where(
                BalanceRecord.provider == "finastra",
                BalanceRecord.account_external_id == b.account_external_id,
                BalanceRecord.as_of_ts == as_of,
            )
        ).first()
        if existing:
            if existing.source_hash != hsh:
                existing.current_amount = float(b.get("currentAmount", 0))
                existing.available_amount = float(b.get("availableAmount", 0)) if b.get("availableAmount") else None
                existing.credit_limit_amount = float(b.get("creditLimitAmount", 0)) if b.get("creditLimitAmount") else None
                existing.currency = b.get("currency")
                existing.source_hash = hsh
                updated += 1
            else:
                skipped += 1
        else:
            sess.add(
                BalanceRecord(
                    provider="finastra",
                    account_external_id=b.account_external_id,
                    as_of_ts=as_of,
                    current_amount=float(b.get("currentAmount", 0)),
                    available_amount=float(b.get("availableAmount", 0)) if b.get("availableAmount") else None,
                    credit_limit_amount=float(b.get("creditLimitAmount", 0)) if b.get("creditLimitAmount") else None,
                    currency=b.get("currency"),
                    source_hash=hsh,
                )
            )
            created += 1
    sess.commit()
    for lbl, val in {"created": created, "updated": updated, "skipped": skipped}.items():
        if val:
            _BAL_UPSERT_TOTAL.labels(result=lbl).inc(val)


# Syncer -------------------------------------------------------------------

class FinastraBalancesSyncer:
    def __init__(self, *, client: BalancesClient, session_factory: Callable[[], Session]):
        self._client = client
        self._session_factory = session_factory

    async def _account_ids(self) -> List[str]:
        with self._session_factory() as sess:
            rows = sess.exec(select(AccountRecord.external_id)).all()
        return [r[0] if isinstance(r, tuple) else r for r in rows]

    async def run_once(self, account_ids: Optional[List[str]] = None) -> int:
        ids = account_ids or await self._account_ids()
        processed = 0
        async for balances_page in self._client.list_all_balances(ids):
            with self._session_factory() as sess:
                _upsert_batch(sess, balances_page)
            processed += len(balances_page)
        _BAL_LAST_SUCCESS.set_to_current_time()
        return processed
