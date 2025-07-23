"""Common Prometheus metrics for the treasury stack."""

from prometheus_client import start_http_server, Gauge, Histogram, Summary

# Export metrics on port 8001 when this module is imported
start_http_server(8001)

# Gauge for loan-to-value ratios keyed by bank id
treas_ltv_ratio = Gauge(
    "treas_ltv_ratio", "Loan-to-Value ratio", ["bank_id"]
)

# Histogram measuring sweep execution latency
sweep_latency_seconds = Histogram(
    "sweep_latency_seconds", "Latency of sweep execution in seconds"
)

# Summary measuring credit draw latency
credit_draw_latency_seconds = Summary(
    "credit_draw_latency_seconds", "Latency of credit draw operations in seconds"
)
