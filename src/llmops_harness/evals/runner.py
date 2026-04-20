"""Tiny eval runner.

A suite is a YAML file with a list of cases. Each case has a prompt, an
optional expected substring, and a tag. The runner calls the wrapped client,
computes a pass/fail, and emits a summary plus per-case JSON.

Scoring here is intentionally naive — substring match. The point of v0.1 is
to wire the pipeline end-to-end. Swap in real scorers (LLM-as-judge, exact
match, rubric) in later versions.
"""

from __future__ import annotations

import argparse
import json
import statistics
import sys
import time
from pathlib import Path
from typing import Any

import yaml

from ..budget import BudgetTracker
from ..client import CompletionRequest, LLMClient
from ..tracing import configure as configure_tracing


def load_suite(path: Path) -> dict[str, Any]:
    with path.open() as f:
        return yaml.safe_load(f)


def score(case: dict[str, Any], text: str) -> dict[str, Any]:
    must = case.get("must_include", [])
    missing = [m for m in must if m.lower() not in text.lower()]
    passed = len(missing) == 0
    return {"passed": passed, "missing": missing}


def run_suite(suite_path: Path, out_dir: Path) -> int:
    configure_tracing()
    suite = load_suite(suite_path)
    client = LLMClient(budget=BudgetTracker())

    provider = suite["provider"]
    model = suite["model"]
    results: list[dict[str, Any]] = []

    for case in suite["cases"]:
        req = CompletionRequest(
            provider=provider,
            model=model,
            prompt=case["prompt"],
            system=case.get("system"),
            max_tokens=case.get("max_tokens", 512),
            temperature=case.get("temperature", 0.2),
        )
        t0 = time.perf_counter()
        try:
            result = client.complete(req)
            sc = score(case, result.text)
            results.append({
                "id": case["id"],
                "tag": case.get("tag"),
                "passed": sc["passed"],
                "missing": sc["missing"],
                "latency_s": result.latency_seconds,
                "cost_usd": result.cost_usd,
                "input_tokens": result.input_tokens,
                "output_tokens": result.output_tokens,
                "text": result.text,
            })
        except Exception as exc:  # noqa: BLE001
            results.append({
                "id": case["id"],
                "tag": case.get("tag"),
                "passed": False,
                "error": str(exc),
                "latency_s": time.perf_counter() - t0,
            })

    out_dir.mkdir(parents=True, exist_ok=True)
    stamp = time.strftime("%Y%m%dT%H%M%S")
    out_path = out_dir / f"{suite_path.stem}-{stamp}.json"
    summary = _summarize(results)
    payload = {"suite": suite["name"], "provider": provider, "model": model,
               "summary": summary, "results": results}
    out_path.write_text(json.dumps(payload, indent=2))

    print(f"\n{suite['name']} — {provider}/{model}")
    print(f"  passed:     {summary['passed']}/{summary['total']}")
    print(f"  p50 latency: {summary['p50_latency']:.2f}s")
    print(f"  p95 latency: {summary['p95_latency']:.2f}s")
    print(f"  total cost:  ${summary['total_cost_usd']:.4f}")
    print(f"  → {out_path}")

    return 0 if summary["passed"] == summary["total"] else 1


def _summarize(results: list[dict[str, Any]]) -> dict[str, Any]:
    total = len(results)
    passed = sum(1 for r in results if r.get("passed"))
    latencies = sorted(r["latency_s"] for r in results if "latency_s" in r)
    total_cost = sum(r.get("cost_usd", 0.0) for r in results)
    return {
        "total": total,
        "passed": passed,
        "p50_latency": statistics.median(latencies) if latencies else 0.0,
        "p95_latency": latencies[int(len(latencies) * 0.95)] if latencies else 0.0,
        "total_cost_usd": total_cost,
    }


def main() -> None:
    parser = argparse.ArgumentParser(prog="llmops_harness.evals")
    parser.add_argument("--suite", required=True, type=Path)
    parser.add_argument("--out", default=Path("evals/outputs"), type=Path)
    args = parser.parse_args()
    sys.exit(run_suite(args.suite, args.out))
