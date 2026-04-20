"""Smoke tests for metrics registration. No network."""

from llmops_harness import metrics


def test_all_metric_families_register():
    """Every declared metric must appear as a family in the registry.

    Note: Prometheus strips the `_total` suffix from counter family names,
    so we check the base name. Labeled metrics emit no samples until used,
    which is why we assert on family presence rather than sample content.
    """
    family_names = {family.name for family in metrics.registry.collect()}
    expected = {
        "llm_request_duration_seconds",
        "llm_tokens",             # from llm_tokens_total
        "llm_cost_usd",           # from llm_cost_usd_total
        "llm_requests",           # from llm_requests_total
        "llm_budget_exceeded",    # from llm_budget_exceeded_total
        "llm_cache_hits",         # from llm_cache_hits_total
    }
    missing = expected - family_names
    assert not missing, f"missing metric families: {missing}"


def test_incremented_counter_emits_sample():
    """Sanity: once we increment a labeled counter, its samples appear."""
    metrics.requests_total.labels(provider="test", model="test", status="ok").inc()
    samples = {s.name for family in metrics.registry.collect() for s in family.samples}
    assert "llm_requests_total" in samples


def test_histogram_records_observation():
    metrics.request_duration_seconds.labels(
        provider="test", model="test", status="ok"
    ).observe(0.42)
    samples = {s.name for family in metrics.registry.collect() for s in family.samples}
    assert "llm_request_duration_seconds_bucket" in samples
    assert "llm_request_duration_seconds_sum" in samples
    assert "llm_request_duration_seconds_count" in samples
