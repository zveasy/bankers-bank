from prometheus_client import start_http_server, Gauge, Histogram, Summary, REGISTRY

# Only start the HTTP server once per process
import threading

# Only start the HTTP server once per process using a module-level variable
if not globals().get("_prometheus_server_started", False):
    start_http_server(8001)
    globals()["_prometheus_server_started"] = True

def get_metric(cls, name, *args, **kwargs):
    # Avoid duplicate registration by checking if metric exists
    try:
        return REGISTRY._names_to_collectors[name]
    except KeyError:
        return cls(name, *args, **kwargs)

# Gauge for loan-to-value ratios keyed by bank id
treas_ltv_ratio = get_metric(Gauge, "treas_ltv_ratio", "Loan-to-Value ratio", ["bank_id"])

# Histogram measuring sweep execution latency
sweep_latency_seconds = get_metric(Histogram, "sweep_latency_seconds", "Latency of sweep execution in seconds")

# Summary measuring credit draw latency
credit_draw_latency_seconds = get_metric(Summary, "credit_draw_latency_seconds", "Latency of credit draw operations in seconds")