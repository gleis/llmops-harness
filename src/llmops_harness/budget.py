"""Token and cost budgets. Fail loud, never silent."""

from dataclasses import dataclass, field

from .metrics import budget_exceeded_total
from .settings import settings


class BudgetExceeded(Exception):
    """Raised when a hard cap is hit. Catch at the API boundary."""


@dataclass
class BudgetTracker:
    """Tracks spend within a logical session (e.g., one user conversation)."""

    session_cost_usd: float = 0.0
    max_tokens_per_request: int = field(
        default_factory=lambda: settings.budget_max_tokens_per_request
    )
    max_cost_per_request: float = field(
        default_factory=lambda: settings.budget_max_cost_usd_per_request
    )
    max_cost_per_session: float = field(
        default_factory=lambda: settings.budget_max_cost_usd_per_session
    )

    def check_request_tokens(self, expected_tokens: int) -> None:
        if expected_tokens > self.max_tokens_per_request:
            budget_exceeded_total.labels(budget="request_tokens").inc()
            raise BudgetExceeded(
                f"request exceeds token budget: "
                f"{expected_tokens} > {self.max_tokens_per_request}"
            )

    def check_request_cost(self, expected_cost: float) -> None:
        if expected_cost > self.max_cost_per_request:
            budget_exceeded_total.labels(budget="request_cost").inc()
            raise BudgetExceeded(
                f"request exceeds cost budget: "
                f"${expected_cost:.4f} > ${self.max_cost_per_request:.4f}"
            )

    def record(self, cost_usd: float) -> None:
        self.session_cost_usd += cost_usd
        if self.session_cost_usd > self.max_cost_per_session:
            budget_exceeded_total.labels(budget="session_cost").inc()
            raise BudgetExceeded(
                f"session exceeds cost budget: "
                f"${self.session_cost_usd:.4f} > ${self.max_cost_per_session:.4f}"
            )
