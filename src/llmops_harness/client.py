"""Wrapped LLM client.

The point of this module is NOT to add features. It's to make sure every LLM
call in the system goes through one funnel that emits metrics, traces, enforces
budgets, and retries with sane rules. The rest of the app should never call
LiteLLM directly.
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any

import litellm
import structlog
from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

from .budget import BudgetExceeded, BudgetTracker
from .metrics import cost_usd_total, request_duration_seconds, requests_total, tokens_total
from .tracing import tracer

log = structlog.get_logger()


@dataclass
class CompletionRequest:
    provider: str                 # "anthropic" | "openai" | "google" | "ollama"
    model: str                    # e.g. "claude-sonnet-4-6" | "llama3.2"
    prompt: str
    system: str | None = None
    max_tokens: int = 1024
    temperature: float = 0.2


@dataclass
class CompletionResult:
    text: str
    input_tokens: int
    output_tokens: int
    cost_usd: float
    latency_seconds: float
    model: str
    provider: str


class _TransientError(Exception):
    """Provider errors that should be retried."""


def _classify(exc: Exception) -> str:
    name = type(exc).__name__.lower()
    if "ratelimit" in name or "429" in str(exc):
        return "rate_limit"
    if "timeout" in name:
        return "timeout"
    if "context" in name and "length" in str(exc).lower():
        return "context_length"
    if "auth" in name or "401" in str(exc) or "403" in str(exc):
        return "auth"
    return "provider_error"


def _litellm_model_id(req: CompletionRequest) -> str:
    """Build the provider-prefixed model string LiteLLM expects."""
    if req.provider == "ollama":
        return f"ollama/{req.model}"
    if req.provider == "anthropic":
        return f"anthropic/{req.model}"
    if req.provider == "openai":
        return req.model                      # LiteLLM treats bare strings as OpenAI
    if req.provider == "google":
        return f"gemini/{req.model}"
    return req.model


class LLMClient:
    """Facade over LiteLLM that emits metrics, traces, and enforces budgets."""

    def __init__(self, budget: BudgetTracker | None = None) -> None:
        self.budget = budget or BudgetTracker()

    @retry(
        retry=retry_if_exception_type(_TransientError),
        wait=wait_exponential(multiplier=0.5, min=0.5, max=8),
        stop=stop_after_attempt(4),
        reraise=True,
    )
    def complete(self, req: CompletionRequest) -> CompletionResult:
        labels = {"provider": req.provider, "model": req.model}
        model_id = _litellm_model_id(req)

        messages: list[dict[str, Any]] = []
        if req.system:
            messages.append({"role": "system", "content": req.system})
        messages.append({"role": "user", "content": req.prompt})

        # Budgets that can be checked before the call.
        self.budget.check_request_tokens(req.max_tokens)

        start = time.perf_counter()
        with tracer.start_as_current_span("llm.complete") as span:
            span.set_attributes({
                "llm.provider": req.provider,
                "llm.model": req.model,
                "llm.max_tokens": req.max_tokens,
                "llm.temperature": req.temperature,
            })
            try:
                response = litellm.completion(
                    model=model_id,
                    messages=messages,
                    max_tokens=req.max_tokens,
                    temperature=req.temperature,
                )
            except BudgetExceeded:
                raise
            except Exception as exc:
                latency = time.perf_counter() - start
                status = _classify(exc)
                request_duration_seconds.labels(**labels, status=status).observe(latency)
                requests_total.labels(**labels, status=status).inc()
                span.record_exception(exc)
                log.warning("llm.error", status=status, error=str(exc), **labels)
                if status in {"rate_limit", "timeout", "provider_error"}:
                    raise _TransientError(str(exc)) from exc
                raise

            latency = time.perf_counter() - start
            text = response["choices"][0]["message"]["content"] or ""
            usage = response.get("usage") or {}
            input_tokens = int(usage.get("prompt_tokens") or 0)
            output_tokens = int(usage.get("completion_tokens") or 0)

            cost_usd = 0.0
            try:
                # LiteLLM computes cost when it knows the model pricing.
                cost_usd = float(litellm.completion_cost(completion_response=response) or 0.0)
            except Exception:  # noqa: BLE001 — cost unknown for some local models
                cost_usd = 0.0

            # Post-call budget check (so we stop a runaway session).
            self.budget.record(cost_usd)

            # Metrics
            request_duration_seconds.labels(**labels, status="ok").observe(latency)
            requests_total.labels(**labels, status="ok").inc()
            tokens_total.labels(**labels, kind="input").inc(input_tokens)
            tokens_total.labels(**labels, kind="output").inc(output_tokens)
            cost_usd_total.labels(**labels).inc(cost_usd)

            span.set_attributes({
                "llm.input_tokens": input_tokens,
                "llm.output_tokens": output_tokens,
                "llm.cost_usd": cost_usd,
                "llm.latency_s": latency,
            })

            log.info(
                "llm.ok",
                latency_s=round(latency, 3),
                input_tokens=input_tokens,
                output_tokens=output_tokens,
                cost_usd=round(cost_usd, 6),
                **labels,
            )

            return CompletionResult(
                text=text,
                input_tokens=input_tokens,
                output_tokens=output_tokens,
                cost_usd=cost_usd,
                latency_seconds=latency,
                model=req.model,
                provider=req.provider,
            )
