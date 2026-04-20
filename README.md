# llmops-harness

A small, opinionated Python service that wraps LLM calls with the things production systems need: metrics, traces, token/cost budgets, structured retries, and a replayable eval harness.

Built as the substrate for RAG and agent systems — not the end product. If you can't see it, you can't trust it. If you can't budget it, it will bankrupt you. This repo is the "see it" and "budget it" layer.

![llmops-harness dashboard — request rate, latency p50/p95/p99, cost, token throughput, budget trips, error rate by class](docs/dashboard.png)

*Live Grafana dashboard after a handful of calls against local Ollama (llama3.2). Cost line is flat at $0 because Ollama is free; swap in a paid provider and it lifts off. Budget trips and error rate show **0** — the "no bad news" signal, not missing data.*

## What's in the box

- **Multi-provider client** (LiteLLM) — Claude, GPT, Gemini, and local Ollama behind one interface
- **Prometheus metrics** — latency histograms, token counts, cost per call, error classes, cache hits
- **OpenTelemetry tracing** — end-to-end spans across chained calls (so a multi-step agent is debuggable)
- **Token + cost budgets** — hard caps per request and per session; fail loudly, not silently
- **Retry policy** — exponential backoff with per-error-class rules (rate limit vs. provider error vs. context length)
- **Eval harness** — YAML-defined suites replayed on demand; emits quality scores alongside cost and latency
- **Grafana dashboard** — ships as JSON in the repo (see screenshot above)
- **Docker-compose observability stack** — Prometheus + Grafana + Jaeger, up in one command

## Why this exists

Most LLM demo code looks like `client.chat(messages)` in a notebook. Most LLM production code looks like an on-call engineer wondering why the p99 latency is 40 seconds and why the bill is $8,000 and nobody knows which feature did it. This repo is the shape that sits in between.

## Quickstart

```bash
# Clone and install
git clone <your-repo-url>
cd llmops-harness
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"

# Stand up the observability stack (Prometheus + Grafana + Jaeger)
docker compose -f deploy/docker-compose.yml up -d

# Copy env template and fill in your provider keys
cp .env.example .env

# Run the wrapped server
uvicorn llmops_harness.server:app --reload

# Hit it
curl -X POST http://localhost:8000/v1/complete \
  -H "Content-Type: application/json" \
  -d '{"provider": "ollama", "model": "llama3.2", "prompt": "Say hi."}'

# Replay the eval suite
python -m llmops_harness.evals --suite evals/suites/basic.yaml

# View metrics and traces
open http://localhost:3000        # Grafana (admin/admin)
open http://localhost:16686       # Jaeger
open http://localhost:9090        # Prometheus
```

## Metrics exposed

| Metric | Type | Labels | Purpose |
|--------|------|--------|---------|
| `llm_request_duration_seconds` | Histogram | provider, model, status | p50/p95/p99 latency |
| `llm_tokens_total` | Counter | provider, model, kind (input/output) | Token volume |
| `llm_cost_usd_total` | Counter | provider, model | Running spend |
| `llm_requests_total` | Counter | provider, model, status | Request volume + error rate |
| `llm_budget_exceeded_total` | Counter | budget (request/session) | Hard-limit trips |
| `llm_cache_hits_total` | Counter | provider, model | Cache effectiveness |

The Grafana dashboard in `dashboards/llmops-harness.json` renders all of these as a single board.

## Project status

**v0.1 — scaffolding.** Core client, metrics, tracing, budget module, one eval suite, docker-compose stack. Next up: v0.2 adds a reference RAG handler, v0.3 adds a simple HITL-gated agent runner.

## License

MIT.
