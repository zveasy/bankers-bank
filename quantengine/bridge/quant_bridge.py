"""Stubbed Quant bridge publisher.

No Kafka or network dependency: a pluggable *transport* callable is used so
unit-tests can inject a fake implementation.
"""
from __future__ import annotations

import json
import os
import time
from datetime import datetime, timezone
from typing import Callable, Dict, Protocol

try:
    # Only import metrics when available; fall back to no-ops in unit tests.
    from treasury_observability.metrics import \
        quant_circuit_open as _circuit_gauge
    from treasury_observability.metrics import \
        quant_publish_latency_seconds as _latency_hist
    from treasury_observability.metrics import \
        quant_publish_total as _publish_counter
except Exception:  # pragma: no cover

    class _NoopMetric:  # pylint: disable=too-few-public-methods
        def labels(self, *_, **__):
            return self

        def observe(self, *_):
            return None

        def inc(self, *_):
            return None

    _latency_hist = _NoopMetric()  # type: ignore
    _publish_counter = _NoopMetric()  # type: ignore


class Transport(Protocol):
    """Callable transport signature."""

    def __call__(self, topic: str, key: bytes, value: bytes) -> None:
        ...


# Default no-op transport ----------------------------------------------------


def _noop_transport(topic: str, key: bytes, value: bytes) -> None:  # noqa: D401
    """Do nothing (dry-run)."""


# Main publish API -----------------------------------------------------------


def publish_cash_position(
    payload: Dict[str, object],
    *,
    dry_run: bool = True,
    kafka_bootstrap: str | None = None,  # noqa: ARG001 – future use
    topic: str = "cash_positions",
    transport: Transport | None = None,
) -> Dict[str, object]:
    """Publish *payload* to Quant bridge or simulate via *dry_run*.

    The key is deterministic: ``"{bank_id}|{asof_ts}"``.
    Latency + result counters are recorded via Prometheus.
    """
    # Circuit breaker check
    circuit_open = os.getenv("QUANT_CIRCUIT_OPEN", "0").strip().lower() in {
        "1",
        "true",
        "yes",
    }
    try:
        _circuit_gauge.set(1 if circuit_open else 0)
    except Exception:
        pass

    start_ts = time.perf_counter()

    bank_id = str(payload.get("bank_id", ""))
    asof_ts = str(payload.get("asof_ts", datetime.now(timezone.utc).isoformat()))
    key = f"{bank_id}|{asof_ts}"

    result = "success"
    try:
        if circuit_open:
            _publish_counter.labels(result="skipped").inc()
            return {"ok": True, "skipped": True, "key": key}

        if dry_run:
            # simulate
            _publish_counter.labels(result=result).inc()
            return {"ok": True, "dry_run": True, "key": key}

        # Real publish path
        if transport is None:
            raise RuntimeError("Real publish requested but no transport provided")
        transport(topic, key.encode(), json.dumps(payload).encode())
        _publish_counter.labels(result=result).inc()
        return {"ok": True, "dry_run": False, "key": key}

    except Exception as exc:  # pragma: no cover
        result = "error"
        _publish_counter.labels(result=result).inc()
        raise exc

    finally:
        elapsed = time.perf_counter() - start_ts
        _latency_hist.labels(path=topic).observe(elapsed)
