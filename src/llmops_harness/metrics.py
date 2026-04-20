"""Prometheus metrics. These are the dials on the dashboard."""

from prometheus_client import CollectorRegistry, Counter, Histogram

registry = CollectorRegistry()

# Latency buckets tuned for LLM calls. Short-tail under 1s (rare for real calls)
# up through 60s (long agent chains). Adjust if your workload is different.
LATENCY_BUCKETS = (
    0.1, 0.25, 0.5, 1, 2, 3, 5, 8, 13, 21, 34, 60,
)

request_duration_seconds = Histogram(
    "llm_request_duration_seconds",
    "End-to-end duration of an LLM call.",
    labelnames=("provider", "model", "status"),
    buckets=LATENCY_BUCKETS,
    registry=registry,
)

tokens_total = Counter(
    "llm_tokens_total",
    "Total tokens consumed, split by direction.",
    labelnames=("provider", "model", "kind"),  # kind = input | output
    registry=registry,
)

cost_usd_total = Counter(
    "llm_cost_usd_total",
    "Running cost in USD per provider/model.",
    labelnames=("provider", "model"),
    registry=registry,
)

requests_total = Counter(
    "llm_requests_total",
    "Request count by status (ok | error class).",
    labelnames=("provider", "model", "status"),
    registry=registry,
)

budget_exceeded_total = Counter(
    "llm_budget_exceeded_total",
    "Hard-cap trips by budget type.",
    labelnames=("budget",),  # budget = request_tokens | request_cost | session_cost
    registry=registry,
)

cache_hits_total = Counter(
    "llm_cache_hits_total",
    "Response cache hits.",
    labelnames=("provider", "model"),
    registry=registry,
)
