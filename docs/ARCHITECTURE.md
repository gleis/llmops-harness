# Architecture

```
               ┌────────────────────────────────┐
               │   FastAPI  /v1/complete        │
               └────────────────┬───────────────┘
                                │
                                ▼
               ┌────────────────────────────────┐
               │         LLMClient              │
               │  ┌──────────────────────────┐  │
               │  │ BudgetTracker            │  │──► /metrics (Prometheus)
               │  │  pre-call token cap      │  │
               │  │  pre-call cost cap       │  │
               │  │  post-call session cap   │  │
               │  └──────────────────────────┘  │
               │  ┌──────────────────────────┐  │
               │  │ OpenTelemetry span       │  │──► OTLP → Jaeger
               │  │  llm.* attributes        │  │
               │  └──────────────────────────┘  │
               │  ┌──────────────────────────┐  │
               │  │ Tenacity retry           │  │
               │  │  rate_limit / timeout    │  │
               │  │  provider_error          │  │
               │  └──────────────────────────┘  │
               │  ┌──────────────────────────┐  │
               │  │ LiteLLM                  │──┼──► Anthropic / OpenAI / Gemini / Ollama
               │  └──────────────────────────┘  │
               └────────────────┬───────────────┘
                                │
                                ▼
                  ┌──────────── metrics ────────────┐
                  │ request_duration  tokens         │
                  │ cost_usd          requests        │
                  │ budget_exceeded   cache_hits      │
                  └──────────────────────────────────┘
```

## Design choices

**Why LiteLLM instead of wrapping each SDK.** The point of this repo is
observability, not provider abstraction. LiteLLM handles provider quirks so
the interesting code (metrics, budgets, retries) stays single-purpose.

**Why pre-call and post-call budget checks.** Pre-call catches oversize
requests before a token is spent. Post-call catches session-wide drift
(many cheap requests adding up).

**Why classify errors instead of retrying everything.** Retrying a 400 with
a context-length error wastes time and money. The client retries only the
classes where retry has a chance of working.

**Why the metrics have `(provider, model)` as the primary cardinality.**
Cost and latency vary wildly by model. A single "latency" chart hides the
fact that claude-3.5-haiku is 10× faster than claude-3-opus. Keep them split.

## Non-goals for v0.1

- Streaming responses (planned for v0.2 when a RAG handler is added)
- Caching (hooks exist — `cache_hits_total` — but no implementation yet)
- Rate-limiting *inbound* requests (use a reverse proxy for that)
- Multi-tenant budgets (one session-tracker per process for now)
