"""Prometheus business metrics for NLWeb core.

These metrics are populated by the handler and LLM modules.
They use the global prometheus_client registry, so they are automatically
included when generate_latest() is called at the /metrics endpoint
exposed by the network layer.
"""

from prometheus_client import Histogram

ASK_RESULTS_RETURNED = Histogram(
    "ask_results_returned",
    "Number of results returned per /ask request",
    buckets=[0, 1, 2, 3, 5, 10, 15, 20, 30, 50],
)

ASK_QUERY_LENGTH_CHARS = Histogram(
    "ask_query_length_chars",
    "Character length of incoming query text",
    buckets=[10, 25, 50, 100, 200, 500, 1000, 2000],
)

ASK_RETRIEVAL_DURATION = Histogram(
    "ask_retrieval_duration_seconds",
    "Duration of vector search retrieval stage",
    buckets=[0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0],
)

ASK_SCORING_DURATION = Histogram(
    "ask_scoring_duration_seconds",
    "Duration of LLM scoring/ranking stage",
    buckets=[0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0, 30.0],
)

ASK_LLM_CALL_DURATION = Histogram(
    "ask_llm_call_duration_seconds",
    "Duration of individual LLM calls",
    labelnames=["operation"],
    buckets=[0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0, 30.0],
)
