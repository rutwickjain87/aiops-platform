"""
run_eval_ci.py — CI wrapper around the log-intelligence evaluator.

Called by `make eval` from the repo root. Runs the agent eval suite,
writes results to a JSON file the GitHub Actions workflow can read,
and exits non-zero if pass rate falls below the threshold.

Usage:
    python scripts/run_eval_ci.py \
        --backend anthropic \
        --threshold 0.80 \
        --output evals/results/latest.json

Output JSON shape (matches the PR comment script in eval.yaml):
{
  "pass_rate": 1.0,
  "passed": 5,
  "total": 5,
  "avg_cost_usd": 0.0,
  "p95_latency_ms": 12345,
  "failed": []
}
"""
from __future__ import annotations

import argparse
import json
import statistics
import sys
from pathlib import Path

# Make the agent importable from the repo root
AGENT_DIR = Path(__file__).parent.parent / "agents" / "log-intelligence"
sys.path.insert(0, str(AGENT_DIR))


def make_agent(backend: str):
    """Construct a fresh agent for the given backend. Requires API keys in env."""
    if backend == "anthropic":
        from planner_anthropic import AnthropicPlanner, AnthropicPlannerConfig, SYSTEM_PROMPT
        from tools_anthropic import Tools
        from memory_anthropic import Memory
        return AnthropicPlanner(
            tools=Tools(),
            memory=Memory(system_prompt=SYSTEM_PROMPT),
            config=AnthropicPlannerConfig(),
        )
    if backend == "langchain":
        from planner_langchain import LangChainPlanner, LangChainPlannerConfig, SYSTEM_PROMPT
        from tools_langchain import Tools
        from memory_langchain import Memory
        return LangChainPlanner(
            tools=Tools(),
            memory=Memory(system_prompt=SYSTEM_PROMPT),
            config=LangChainPlannerConfig(),
        )
    if backend == "openrouter":
        from planner_openrouter import OpenRouterPlanner, OpenRouterPlannerConfig, SYSTEM_PROMPT
        from tools_openrouter import Tools
        from memory_openrouter import Memory
        return OpenRouterPlanner(
            tools=Tools(),
            memory=Memory(system_prompt=SYSTEM_PROMPT),
            config=OpenRouterPlannerConfig(),
        )
    raise ValueError(f"Unknown backend: {backend!r}")


def main() -> int:
    parser = argparse.ArgumentParser(description="CI eval runner for log-intelligence agent.")
    parser.add_argument("--backend",   default="anthropic",
                        choices=["anthropic", "langchain", "openrouter"])
    parser.add_argument("--threshold", type=float, default=0.80,
                        help="Minimum pass rate required (0–1). Default: 0.80")
    parser.add_argument("--output",    default="evals/results/latest.json",
                        help="Path to write the results JSON.")
    parser.add_argument("--sleep",     type=float, default=2.0,
                        help="Seconds between cases (default: 2).")
    args = parser.parse_args()

    from evaluator import Evaluator

    # Change cwd to agent dir so relative paths (evals/cases.jsonl) work
    import os
    os.chdir(AGENT_DIR)

    ev = Evaluator(
        agent_factory=lambda: make_agent(args.backend),
        cases_path="evals/cases.jsonl",
        sleep_between_cases=args.sleep,
    )
    results = ev.run()

    total  = len(results)
    passed = sum(1 for r in results if r.passed)
    failed = [r.case_id for r in results if not r.passed]
    pass_rate = passed / total if total else 0.0

    latencies = [r.latency_ms for r in results if r.latency_ms > 0]
    p95_ms = (
        sorted(latencies)[min(int(len(latencies) * 0.95), len(latencies) - 1)]
        if latencies else 0
    )
    avg_cost = sum(r.cost_usd for r in results) / total if total else 0.0

    payload = {
        "pass_rate":     pass_rate,
        "passed":        passed,
        "total":         total,
        "avg_cost_usd":  avg_cost,
        "p95_latency_ms": p95_ms,
        "failed":        failed,
        "backend":       args.backend,
    }

    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(payload, indent=2))
    print(f"\nResults written to {output_path}")

    if pass_rate < args.threshold:
        print(
            f"\n❌  Pass rate {pass_rate:.0%} is below threshold {args.threshold:.0%}. "
            f"Failed cases: {failed}",
            file=sys.stderr,
        )
        return 1

    print(f"\n✅  Pass rate {pass_rate:.0%} meets threshold {args.threshold:.0%}.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
