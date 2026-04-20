"""Unit tests for the budget tracker. Fast, no network."""

import pytest

from llmops_harness.budget import BudgetExceeded, BudgetTracker


def test_request_token_budget_blocks_oversize_request():
    b = BudgetTracker(max_tokens_per_request=100)
    with pytest.raises(BudgetExceeded):
        b.check_request_tokens(101)


def test_request_token_budget_allows_within_limit():
    b = BudgetTracker(max_tokens_per_request=100)
    b.check_request_tokens(100)  # should not raise


def test_request_cost_budget_blocks_expensive_call():
    b = BudgetTracker(max_cost_per_request=0.10)
    with pytest.raises(BudgetExceeded):
        b.check_request_cost(0.11)


def test_session_cost_budget_trips_on_accumulation():
    b = BudgetTracker(max_cost_per_session=1.00)
    b.record(0.40)
    b.record(0.40)
    with pytest.raises(BudgetExceeded):
        b.record(0.21)  # cumulative 1.01 > 1.00


def test_session_cost_records_below_cap():
    b = BudgetTracker(max_cost_per_session=1.00)
    b.record(0.99)
    assert b.session_cost_usd == pytest.approx(0.99)
