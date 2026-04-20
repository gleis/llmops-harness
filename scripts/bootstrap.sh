#!/usr/bin/env bash
# bootstrap.sh — zero-to-dashboard in one command.
#
# What it does:
#   1. Verifies prerequisites (python 3.10+, docker, ollama)
#   2. Creates .venv and installs the package
#   3. Copies .env.example → .env if missing
#   4. Starts Prometheus + Grafana + Jaeger via docker compose
#   5. Pulls the Ollama model if needed
#   6. Starts uvicorn in the background (PID in .run/uvicorn.pid)
#   7. Runs the smoke script to populate metrics
#   8. Prints URLs for the three UIs
#
# Safe to re-run. Teardown: scripts/teardown.sh

set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

RUN_DIR="$ROOT/.run"
mkdir -p "$RUN_DIR"
UVICORN_PID_FILE="$RUN_DIR/uvicorn.pid"
UVICORN_LOG="$RUN_DIR/uvicorn.log"

MODEL="${MODEL:-llama3.2}"

say()  { printf "\033[1;34m→\033[0m %s\n" "$*"; }
ok()   { printf "\033[1;32m✓\033[0m %s\n" "$*"; }
warn() { printf "\033[1;33m!\033[0m %s\n" "$*"; }
fail() { printf "\033[1;31m✗\033[0m %s\n" "$*" >&2; exit 1; }

# --- 1. Prereqs -------------------------------------------------------------

say "Checking prerequisites"

if ! command -v python3 >/dev/null; then
  fail "python3 not found. Install Python 3.10+ and retry."
fi
PY_VER=$(python3 -c 'import sys; print(f"{sys.version_info[0]}.{sys.version_info[1]}")')
PY_OK=$(python3 -c 'import sys; print(1 if sys.version_info >= (3,10) else 0)')
if [[ "$PY_OK" != "1" ]]; then
  fail "python3 is $PY_VER; need 3.10+."
fi
ok "python3 $PY_VER"

if ! command -v docker >/dev/null; then
  fail "docker not found. Install Docker Desktop (Mac/Windows) or Docker Engine (Linux) and retry."
fi
if ! docker info >/dev/null 2>&1; then
  fail "docker is installed but the daemon isn't running. Start Docker Desktop / dockerd and retry."
fi
ok "docker running"

if ! command -v ollama >/dev/null; then
  warn "ollama not found. The smoke test needs it."
  warn "Install: https://ollama.com/download  (or: brew install ollama)"
  warn "Skipping smoke step. You can still hit /v1/complete manually with a hosted provider."
  HAS_OLLAMA=0
else
  ok "ollama installed"
  HAS_OLLAMA=1
fi

# --- 2. Virtualenv + install ------------------------------------------------

if [[ ! -d .venv ]]; then
  say "Creating .venv"
  python3 -m venv .venv
fi
# shellcheck disable=SC1091
source .venv/bin/activate

if ! python -c "import llmops_harness" >/dev/null 2>&1; then
  say "Installing llmops-harness (this takes a minute)"
  pip install --quiet --upgrade pip
  pip install --quiet -e ".[dev]"
fi
ok "package installed"

# --- 3. .env ----------------------------------------------------------------

if [[ ! -f .env ]]; then
  cp .env.example .env
  ok ".env created from .env.example"
else
  ok ".env already present"
fi

# --- 4. Obs stack -----------------------------------------------------------

say "Starting Prometheus + Grafana + Jaeger"
docker compose -f deploy/docker-compose.yml up -d >/dev/null
ok "obs stack up (may take 10-20s to be fully ready)"

# --- 5. Ollama model --------------------------------------------------------

if [[ "$HAS_OLLAMA" == "1" ]]; then
  if ! ollama list 2>/dev/null | awk 'NR>1 {print $1}' | grep -q "^${MODEL}$"; then
    say "Pulling Ollama model: $MODEL (first time only, ~2GB)"
    ollama pull "$MODEL"
  fi
  ok "ollama model ready: $MODEL"

  # Make sure the Ollama daemon is actually serving. `ollama serve` runs in its own
  # process on install; if it's not running, `ollama pull` usually starts it.
  if ! curl -sf http://localhost:11434/api/tags >/dev/null; then
    warn "Ollama daemon not responding on :11434. Run 'ollama serve' in another terminal."
  fi
fi

# --- 6. Uvicorn -------------------------------------------------------------

if [[ -f "$UVICORN_PID_FILE" ]] && kill -0 "$(cat "$UVICORN_PID_FILE")" 2>/dev/null; then
  ok "uvicorn already running (pid $(cat "$UVICORN_PID_FILE"))"
else
  say "Starting uvicorn in the background (log: .run/uvicorn.log)"
  nohup uvicorn llmops_harness.server:app --host 0.0.0.0 --port 8000 \
    >"$UVICORN_LOG" 2>&1 &
  echo $! >"$UVICORN_PID_FILE"
  # Wait until /health answers
  for i in {1..20}; do
    if curl -sf http://localhost:8000/health >/dev/null; then break; fi
    sleep 0.5
  done
  if ! curl -sf http://localhost:8000/health >/dev/null; then
    fail "uvicorn failed to come up. See $UVICORN_LOG"
  fi
  ok "uvicorn up (pid $(cat "$UVICORN_PID_FILE"))"
fi

# --- 7. Smoke ---------------------------------------------------------------

if [[ "$HAS_OLLAMA" == "1" ]]; then
  say "Running smoke script (5 calls against $MODEL)"
  MODEL="$MODEL" bash scripts/smoke.sh || warn "smoke script had errors (check output above)"
else
  warn "skipping smoke — no ollama"
fi

# --- 8. Summary -------------------------------------------------------------

cat <<EOF

┌─────────────────────────────────────────────────────────────┐
│  llmops-harness is up.                                      │
│                                                             │
│  Grafana       →  http://localhost:3000  (admin/admin)      │
│    · Dashboard: "llmops-harness" folder                     │
│  Prometheus    →  http://localhost:9090                     │
│  Jaeger        →  http://localhost:16686                    │
│  Harness API   →  http://localhost:8000/docs                │
│                                                             │
│  Stop everything:  bash scripts/teardown.sh                 │
│  uvicorn log:      tail -f .run/uvicorn.log                 │
└─────────────────────────────────────────────────────────────┘
EOF
