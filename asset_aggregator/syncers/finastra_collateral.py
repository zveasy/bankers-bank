from __future__ import annotations

"""Syncer pulling Finastra collateral pages and upserting into DB.

* Offline-friendly (MockTransport).
* Idempotent via `external_updated_ts` and SHA256 `source_hash`.
* Exposes Prometheus counters / gauges.
"""
import asyncio
import hashlib
import json
import os
from typing import AsyncIterator, Callable, List

from prometheus_client import Counter, Gauge
from sqlalchemy import text
from sqlmodel import Session, SQLModel, create_engine

from integrations.finastra.collateral_client import CollateralClient
from treasury_domain.collateral_models import CollateralRecord, FinastraCollateral

DB_URL = os.getenv("COLLATERAL_DB_URL", os.getenv("ASSET_DB_URL", "sqlite:///./asset_aggregator.db"))
engine = create_engine(DB_URL, echo=False)
SQLModel.metadata.create_all(engine)


_COLL_UPSERT_TOTAL = Counter(
    "collateral_upsert_total",
    "Collateral records processed by result",
    labelnames=["result"],
)
_COLL_LAST_SUCCESS = Gauge("collateral_last_success_unixtime", "Unix timestamp of last successful collateral sync")


async def _iter_collateral_pages(client: CollateralClient) -> AsyncIterator[List[FinastraCollateral]]:
    page_token = None
    while True:
        items, page_token = await client.list_collaterals(page_token=page_token)
        if not items:
            break
        yield items
        if not page_token:
            break


def _calc_hash(src: dict) -> str:
    """Return stable SHA256 hash of a subset of the payload."""
    blob = json.dumps(src, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(blob).hexdigest()


def _upsert_batch(session: Session, rows: List[FinastraCollateral]) -> None:
    # Ensure tables exist for this session/engine (idempotent)
    SQLModel.metadata.create_all(session.get_bind(), tables=[CollateralRecord.__table__])
    session.commit()  # refresh connection schema cache
    created = updated = skipped = 0
    for c in rows:
        source_hash = _calc_hash(c.raw)
        existing = session.get(CollateralRecord, c.id)
        if existing:
            if (
                (c.external_updated_ts and existing.external_updated_ts and c.external_updated_ts > existing.external_updated_ts)
                or existing.source_hash != source_hash
            ):
                existing.kind = c.kind
                existing.status = c.status
                existing.currency = c.currency
                existing.amount = c.amount
                existing.valuation_ts = c.valuation_ts
                existing.external_updated_ts = c.external_updated_ts
                existing.raw = c.raw
                existing.source_hash = source_hash
                updated += 1
            else:
                skipped += 1
        else:
            session.add(
                CollateralRecord(
                    id=c.id,
                    bank_id=c.bank_id,
                    kind=c.kind,
                    status=c.status,
                    currency=c.currency,
                    amount=float(c.amount) if c.amount is not None else None,
                    valuation_ts=c.valuation_ts,
                    external_updated_ts=c.external_updated_ts,
                    raw=c.raw,
                    source_hash=source_hash,
                )
            )
            created += 1
    session.commit()
    for label, val in {"created": created, "updated": updated, "skipped": skipped}.items():
        if val:
            _COLL_UPSERT_TOTAL.labels(result=label).inc(val)



class CollateralSyncer:
    """State-less syncer callable from CLI, scheduler, or HTTP trigger."""

    def __init__(self, *, client: CollateralClient, session_factory: Callable[[], Session]):
        self._client = client
        self._session_factory = session_factory

    async def run_once(self) -> int:
        """Synchronize collateral once and return processed row count.
        Ensures tables exist for the engine provided by `session_factory` –
        important when tests wire a fresh in-memory or tmp sqlite engine.
        """
        # Ensure metadata tables are created for the session/engine we're about
        # to use (the global create_all above points to a different default
        # engine and is not sufficient inside isolated unit tests).
        with self._session_factory() as _sess:
            SQLModel.metadata.create_all(_sess.get_bind(), checkfirst=True)

        total = 0
        async for batch in _iter_collateral_pages(self._client):
            with self._session_factory() as sess:
                _upsert_batch(sess, batch)
                sess.commit()
            total += len(batch)
        _COLL_LAST_SUCCESS.set_to_current_time()
        return total


async def sync_collateral() -> int:  # convenience for scripts
    async with CollateralClient() as client:
        syncer = CollateralSyncer(client=client, session_factory=lambda: Session(engine))
        return await syncer.run_once()


if __name__ == "__main__":  # pragma: no cover
    print(asyncio.run(sync_collateral()))
