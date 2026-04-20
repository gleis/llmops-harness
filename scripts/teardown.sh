#!/usr/bin/env bash
# teardown.sh — stop uvicorn and the obs stack cleanly.

set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

if [[ -f .run/uvicorn.pid ]]; then
  PID=$(cat .run/uvicorn.pid)
  if kill -0 "$PID" 2>/dev/null; then
    echo "→ stopping uvicorn (pid $PID)"
    kill "$PID"
    sleep 1
    kill -0 "$PID" 2>/dev/null && kill -9 "$PID" || true
  fi
  rm -f .run/uvicorn.pid
fi

echo "→ stopping docker stack"
docker compose -f deploy/docker-compose.yml down

echo "✓ stopped"
