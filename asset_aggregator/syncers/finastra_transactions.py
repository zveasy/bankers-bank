from __future__ import annotations
"""Sync Finastra Account Information (US) transactions into `AccountTransactionRecord`.

Offline-safe, idempotent (source_hash), Prom metrics; mirrors pattern of
`FinastraAccountsSyncer`.
"""

from decimal import Decimal
import hashlib
import json
import os
from datetime import datetime, timezone
from common.datetime import parse_iso8601
from typing import Callable, List

from prometheus_client import Counter, Gauge
from sqlmodel import SQLModel, Session, create_engine, select

from integrations.finastra.account_info_us_client import AccountInfoUSClient, Transaction
from treasury_domain.transaction_models import AccountTransactionRecord

DB_URL = os.getenv("ASSET_DB_URL", "sqlite:///./asset_aggregator.db")
engine = create_engine(DB_URL, echo=False)
SQLModel.metadata.create_all(engine)

_TX_UPSERT_TOTAL = Counter(
    "fin_tx_upsert_total", "Transaction rows processed", labelnames=["result"]
)
_TX_LAST_SUCCESS = Gauge(
    "fin_tx_last_success_unixtime", "Unix timestamp of last successful tx sync"
)


def _calc_hash(src: dict) -> str:
    blob = json.dumps(src, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(blob).hexdigest()


def _upsert_batch(sess: Session, rows: List[Transaction]):
    created = updated = skipped = 0
    now_utc = datetime.now(timezone.utc).replace(tzinfo=None)
    for tx in rows:
        hsh = _calc_hash(tx.raw)
        existing = sess.exec(
            select(AccountTransactionRecord).where(
                AccountTransactionRecord.provider == "finastra",
                AccountTransactionRecord.account_external_id == tx.account_external_id,
                AccountTransactionRecord.external_tx_id == tx.external_tx_id,
                AccountTransactionRecord.booking_date == parse_iso8601(tx.booking_date).replace(tzinfo=None)
                if tx.booking_date else None,
            )
        ).first()
        # helper to parse optional ts
        def _iso(ts: str | None):
            return (
                parse_iso8601(ts).replace(tzinfo=None)
                if ts else None
            )
        if existing:
            if existing.source_hash != hsh:
                # update mutable fields; immutable IDs/dates stay same
                existing.value_date = _iso(tx.raw.get("valueDate"))
                existing.direction = tx.raw.get("creditDebitIndicator") or tx.direction or existing.direction
                existing.status = tx.raw.get("status") or tx.status
                existing.amount = tx.amount and Decimal(tx.amount)
                existing.currency = tx.currency or existing.currency
                existing.description = tx.description
                existing.reference = tx.reference
                existing.counterparty_name = tx.raw.get("counterpartyName")
                existing.counterparty_account = tx.raw.get("counterpartyAccount")
                existing.scheme = tx.scheme
                existing.category = tx.category
                existing.fx_rate = tx.fx_rate and Decimal(tx.fx_rate)
                existing.fx_src_ccy = tx.fx_src_ccy
                existing.fx_dst_ccy = tx.fx_dst_ccy
                existing.fx_dst_amount = tx.fx_dst_amount and Decimal(tx.fx_dst_amount)
                existing.source_hash = hsh
                existing.last_seen_ts = now_utc
                updated += 1
            else:
                # still refresh watermark
                existing.last_seen_ts = now_utc
                skipped += 1
        else:
            sess.add(
                AccountTransactionRecord(
                    provider="finastra",
                    account_external_id=tx.account_external_id,
                    external_tx_id=tx.external_tx_id,
                    booking_date=_iso(tx.booking_date) or now_utc,
                    value_date=_iso(tx.raw.get("valueDate")),
                    direction=tx.raw.get("creditDebitIndicator") or tx.direction or "DR",
                    status=tx.status,
                    amount=Decimal(tx.amount) if tx.amount else Decimal("0"),
                    currency=tx.currency or "USD",
                    description=tx.description,
                    reference=tx.reference,
                    counterparty_name=tx.raw.get("counterpartyName"),
                    counterparty_account=tx.raw.get("counterpartyAccount"),
                    scheme=tx.scheme,
                    category=tx.category,
                    fx_rate=Decimal(tx.fx_rate) if tx.fx_rate else None,
                    fx_src_ccy=tx.fx_src_ccy,
                    fx_dst_ccy=tx.fx_dst_ccy,
                    fx_dst_amount=Decimal(tx.fx_dst_amount) if tx.fx_dst_amount else None,
                    source_hash=hsh,
                    raw_json=tx.raw,
                    last_seen_ts=now_utc,
                )
            )
            created += 1
    sess.commit()
    for lbl, val in {"created": created, "updated": updated, "skipped": skipped}.items():
        if val:
            _TX_UPSERT_TOTAL.labels(result=lbl).inc(val)


class FinastraTransactionsSyncer:
    def __init__(self, *, client: AccountInfoUSClient, session_factory: Callable[[], Session]):
        self._client = client
        self._session_factory = session_factory

    async def run_once(self, account_ids: list[str], *, since: str | None = None):
        processed = 0
        for acct_id in account_ids:
            async for page in self._client.list_transactions(acct_id, from_date=since):
                with self._session_factory() as sess:
                    _upsert_batch(sess, page)
                processed += len(page)
        _TX_LAST_SUCCESS.set_to_current_time()
        return processed
