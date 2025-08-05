# Move get_metric and _METRICS definition to top so it is available for metric instantiation
from __future__ import annotations
import os
import threading
from typing import Any, Dict, Tuple, Type
from prometheus_client import Gauge, Histogram, Summary, Counter, start_http_server

# Registration helper (avoid duplicate collectors)
_METRICS: Dict[Tuple[Type[Any], str], Any] = {}

def get_metric(cls: Type[Any], name: str, *args, **kwargs):
    key = (cls, name)
    if key in _METRICS:
        return _METRICS[key]
    metric = cls(name, *args, **kwargs)
    _METRICS[key] = metric
    return metric

# Asset snapshot metrics for quant_consumer
asset_snapshots_db_inserts_total = get_metric(
    Counter, "asset_snapshots_db_inserts_total",
    "Total asset snapshot rows inserted (or upserted) into Postgres",
    ["service", "env"]
)

asset_snapshot_process_failures_total = get_metric(
    Counter, "asset_snapshot_process_failures_total",
    "Total failures while processing snapshot messages",
    ["service", "env"]
)

asset_snapshot_process_latency_seconds = get_metric(
    Histogram, "asset_snapshot_process_latency_seconds",
    "Latency to process a single snapshot message end-to-end (seconds)",
    ["service", "env"],
    buckets=(0.05, 0.1, 0.25, 0.5, 1, 2, 5, 10)
)
# treasury_observability/metrics.py
"""
Prometheus metrics for the project.

❗️This module does NOT start a standalone HTTP server.
Expose metrics from each FastAPI app by mounting the ASGI exporter:

    from prometheus_client import make_asgi_app
    app.mount("/metrics", make_asgi_app())

If you ever need a sidecar server (e.g., for a CLI tool), set
METRICS_HTTP_SERVER=1 and import this module — or call
maybe_start_http_server() explicitly.
"""

import os
import threading
from typing import Any, Dict, Tuple, Type

from prometheus_client import Gauge, Histogram, Summary, Counter, start_http_server

# ----------------------------
# Optional standalone server
# ----------------------------
_METRICS_PORT = int(os.getenv("METRICS_PORT", "8001"))
_server_started = False
_server_lock = threading.Lock()


def maybe_start_http_server() -> None:
    """
    Start a sidecar metrics HTTP server (/: /metrics) exactly once,
    but only if METRICS_HTTP_SERVER=1 is set in the environment.

    Normally you should expose metrics via ASGI mounting instead.
    """
    global _server_started
    if _server_started or os.getenv("METRICS_HTTP_SERVER") != "1":
        return
    with _server_lock:
        if not _server_started and os.getenv("METRICS_HTTP_SERVER") == "1":
            start_http_server(_METRICS_PORT)
            _server_started = True


# DO NOT auto-start on import.
# maybe_start_http_server()

# ----------------------------
# Registration helper (avoid duplicate collectors)
# ----------------------------
_METRICS: Dict[Tuple[Type[Any], str], Any] = {}


def get_metric(cls: Type[Any], name: str, *args, **kwargs):
    key = (cls, name)
    if key in _METRICS:
        return _METRICS[key]
    metric = cls(name, *args, **kwargs)
    _METRICS[key] = metric
    return metric


# ----------------------------
# Project metrics
# ----------------------------

# Gauge for loan-to-value ratios keyed by bank id
treas_ltv_ratio = get_metric(
    Gauge,
    "treas_ltv_ratio",
    "Loan-to-Value ratio",
    ["bank_id"],
)

# Histogram measuring sweep execution latency
sweep_latency_seconds = get_metric(
    Histogram,
    "sweep_latency_seconds",
    "Latency of sweep execution in seconds",
    buckets=(0.05, 0.1, 0.25, 0.5, 1, 2, 5, 10),
)

# Summary measuring credit draw latency
credit_draw_latency_seconds = get_metric(
    Summary,
    "credit_draw_latency_seconds",
    "Latency of credit draw operations in seconds",
)

# Counter for number of sweep orders sent
sweeps_total = get_metric(
    Counter,
    "sweeps_total",
    "Number of sweep orders sent",
)

# Histogram for asset snapshot latency
snapshot_latency_seconds = get_metric(
    Histogram,
    "snapshot_latency_seconds",
    "Latency of asset snapshots in seconds",
    buckets=(0.05, 0.1, 0.25, 0.5, 1, 2, 5, 10),
)

# --- Sprint 6 counters ---
snapshot_success_total = get_metric(
    Counter,
    "snapshot_success_total",
    "Number of successful asset snapshots",
    ["bank_id"],
)

snapshot_failure_total = get_metric(
    Counter,
    "snapshot_failure_total",
    "Number of failed asset snapshots",
    ["bank_id"],
)

recon_anomalies_total = get_metric(
    Counter,
    "recon_anomalies_total",
    "Number of reconciliation anomalies detected",
    ["bank_id", "type"],
)

# --- Sprint 7 gauges ---
credit_capacity_available = get_metric(
    Gauge,
    "credit_capacity_available",
    "Available credit facility capacity in USD",
    ["bank_id"],
)

credit_outstanding_total = get_metric(
    Gauge,
    "credit_outstanding_total",
    "Total outstanding credit facility draw in USD",
    ["bank_id"],
)

