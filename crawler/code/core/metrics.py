"""Prometheus metrics for the Crawler master and worker.

Master and worker run in separate processes, so each gets its own
prometheus_client registry. Metrics are defined once here and imported
by whichever process uses them.
"""

from prometheus_client import Counter, Gauge, Histogram

# === HTTP Metrics (master only, via Flask hooks) ===

HTTP_REQUEST_DURATION = Histogram(
    "http_request_duration_seconds",
    "HTTP request latency in seconds",
    labelnames=["method", "endpoint", "status"],
    buckets=[0.01, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0],
)

HTTP_REQUESTS_TOTAL = Counter(
    "http_requests_total",
    "Total number of HTTP requests",
    labelnames=["method", "endpoint", "status"],
)

# === Master Business Metrics ===

CRAWLER_QUEUE_DEPTH = Gauge(
    "crawler_queue_depth",
    "Number of jobs in queue by status",
    labelnames=["status"],
)

CRAWLER_SCHEDULER_RUNS_TOTAL = Counter(
    "crawler_scheduler_runs_total",
    "Total number of scheduler runs",
)

CRAWLER_SCHEDULER_RUN_DURATION = Histogram(
    "crawler_scheduler_run_duration_seconds",
    "Duration of each scheduler run",
    buckets=[1.0, 5.0, 10.0, 30.0, 60.0, 120.0, 300.0],
)

CRAWLER_FILES_QUEUED_TOTAL = Counter(
    "crawler_files_queued_total",
    "Total number of files submitted to processing queue",
)

# === Worker Metrics ===

CRAWLER_JOBS_PROCESSED_TOTAL = Counter(
    "crawler_jobs_processed_total",
    "Total number of jobs processed",
    labelnames=["job_type", "result"],
)

CRAWLER_JOB_DURATION = Histogram(
    "crawler_job_duration_seconds",
    "Duration of job processing",
    labelnames=["job_type"],
    buckets=[1.0, 5.0, 10.0, 30.0, 60.0, 120.0, 300.0, 600.0],
)

CRAWLER_ITEMS_PER_JOB = Histogram(
    "crawler_items_per_job",
    "Number of entities processed per job",
    buckets=[0, 1, 5, 10, 25, 50, 100, 250, 500, 1000],
)

CRAWLER_EXTERNAL_CALL_DURATION = Histogram(
    "crawler_external_call_duration_seconds",
    "Duration of external service calls",
    labelnames=["service"],
    buckets=[0.1, 0.5, 1.0, 2.5, 5.0, 10.0, 30.0, 60.0],
)

CRAWLER_WORKER_IDLE = Gauge(
    "crawler_worker_idle",
    "Whether the worker is idle (1) or processing (0)",
)
