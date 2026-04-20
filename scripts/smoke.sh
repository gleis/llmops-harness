#!/usr/bin/env bash
# Smoke test — hit the running harness a handful of times to populate the dashboard.
# Assumes uvicorn is serving on :8000 and Ollama is running with the model pulled.

set -euo pipefail

URL="${URL:-http://localhost:8000/v1/complete}"
PROVIDER="${PROVIDER:-ollama}"
MODEL="${MODEL:-llama3.2}"

prompts=(
  "Say hi."
  "Name three primary colors."
  "What is 2+2?"
  "Write a one-line Python print statement."
  "List three Kubernetes objects."
)

# Format a JSON response into a one-line summary.
# Pass the response via env var (not stdin) so we don't collide with python3 `-`
# which reads its program from stdin when invoked via heredoc.
format_line() {
  RESPONSE="$1" python3 -c '
import json, os
r = json.loads(os.environ["RESPONSE"])
latency = r.get("latency_seconds", 0.0)
cost = r.get("cost_usd", 0.0)
out = r.get("output_tokens", 0)
print(f"  latency={latency:.2f}s  cost=${cost:.6f}  out={out}tok")
'
}

for p in "${prompts[@]}"; do
  echo "→ $p"
  body=$(python3 -c 'import json, sys; print(json.dumps({"provider": sys.argv[1], "model": sys.argv[2], "prompt": sys.argv[3]}))' "$PROVIDER" "$MODEL" "$p")
  response=$(curl -s -X POST "$URL" -H "Content-Type: application/json" -d "$body")
  if [[ -z "$response" ]]; then
    echo "  (no response — is uvicorn running on :8000?)"
    continue
  fi
  format_line "$response" || echo "  (unparseable response: $response)"
done
