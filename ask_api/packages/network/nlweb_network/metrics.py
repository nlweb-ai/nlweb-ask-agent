"""Prometheus HTTP metrics for the Ask API server.

These metrics are populated by the metrics middleware in server.py.
They use the global prometheus_client registry, so they are automatically
included when generate_latest() is called at the /metrics endpoint.
"""

from prometheus_client import Counter, Gauge, Histogram

HTTP_REQUEST_DURATION = Histogram(
    "http_request_duration_seconds",
    "HTTP request latency in seconds",
    labelnames=["method", "endpoint", "status"],
    buckets=[0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0, 30.0],
)

HTTP_REQUESTS_TOTAL = Counter(
    "http_requests_total",
    "Total number of HTTP requests",
    labelnames=["method", "endpoint", "status"],
)

HTTP_REQUESTS_IN_FLIGHT = Gauge(
    "http_requests_in_flight",
    "Number of HTTP requests currently being processed",
    labelnames=["endpoint"],
)
