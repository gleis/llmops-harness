"""FastAPI wrapper. One /v1/complete endpoint + /metrics + /health.

Intentionally minimal — this is a harness, not a product. If you want a UI,
build it somewhere else and call this.
"""

from __future__ import annotations

from fastapi import FastAPI, HTTPException
from fastapi.responses import Response
from prometheus_client import CONTENT_TYPE_LATEST, generate_latest
from pydantic import BaseModel

from .budget import BudgetExceeded, BudgetTracker
from .client import CompletionRequest, LLMClient
from .metrics import registry
from .tracing import configure as configure_tracing

app = FastAPI(title="llmops-harness", version="0.1.0")
_client: LLMClient | None = None


@app.on_event("startup")
def _startup() -> None:
    global _client
    configure_tracing()
    _client = LLMClient(budget=BudgetTracker())


class CompleteIn(BaseModel):
    provider: str
    model: str
    prompt: str
    system: str | None = None
    max_tokens: int = 1024
    temperature: float = 0.2


class CompleteOut(BaseModel):
    text: str
    input_tokens: int
    output_tokens: int
    cost_usd: float
    latency_seconds: float
    model: str
    provider: str


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok", "service": "llmops-harness"}


@app.get("/metrics")
def metrics() -> Response:
    return Response(generate_latest(registry), media_type=CONTENT_TYPE_LATEST)


@app.post("/v1/complete", response_model=CompleteOut)
def complete(body: CompleteIn) -> CompleteOut:
    assert _client is not None  # startup populated it
    req = CompletionRequest(
        provider=body.provider,
        model=body.model,
        prompt=body.prompt,
        system=body.system,
        max_tokens=body.max_tokens,
        temperature=body.temperature,
    )
    try:
        result = _client.complete(req)
    except BudgetExceeded as exc:
        raise HTTPException(status_code=429, detail=f"budget_exceeded: {exc}") from exc

    return CompleteOut(**result.__dict__)
