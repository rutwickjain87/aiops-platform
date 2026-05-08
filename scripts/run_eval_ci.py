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
import sys
from pathlib import Path

# Make the agent importable from the repo root
REPO_ROOT = Path(__file__).parent.parent
AGENT_DIR = REPO_ROOT / "agents" / "log-intelligence"
sys.path.insert(0, str(AGENT_DIR))


def make_agent(backend: str):
    """Construct a fresh agent for the given backend. Requires API keys in env."""
    if backend == "anthropic":
        from planner_anthropic import (
            AnthropicPlanner,
            AnthropicPlannerConfig,
            SYSTEM_PROMPT,
        )
        from tools_anthropic import Tools
        from memory_anthropic import Memory

        return AnthropicPlanner(
            tools=Tools(),
            memory=Memory(),  # Memory.__init__ takes no args; SYSTEM_PROMPT is in planner
            config=AnthropicPlannerConfig(),
        )
    if backend == "langchain":
        from planner_langchain import (
            LangChainPlanner,
            LangChainPlannerConfig,
            SYSTEM_PROMPT,
        )
        from tools_langchain import Tools
        from memory_langchain import Memory

        return LangChainPlanner(
            tools=Tools(),
            memory=Memory(system_prompt=SYSTEM_PROMPT),
            config=LangChainPlannerConfig(),
        )
    if backend == "openrouter":
        from planner_openrouter import (
            OpenRouterPlanner,
            OpenRouterPlannerConfig,
            SYSTEM_PROMPT,
        )
        from tools_openrouter import Tools
        from memory_openrouter import Memory

        return OpenRouterPlanner(
            tools=Tools(),
            memory=Memory(system_prompt=SYSTEM_PROMPT),
            config=OpenRouterPlannerConfig(),
        )
    raise ValueError(f"Unknown backend: {backend!r}")


def main() -> int:
    parser = argparse.ArgumentParser(
        description="CI eval runner for log-intelligence agent."
    )
    parser.add_argument(
        "--backend",
        default="anthropic",
        choices=["anthropic", "langchain", "openrouter"],
    )
    parser.add_argument(
        "--threshold",
        type=float,
        default=0.80,
        help="Minimum pass rate required (0–1). Default: 0.80",
    )
    parser.add_argument(
        "--output",
        default="evals/results/latest.json",
        help="Path to write the results JSON.",
    )
    parser.add_argument(
        "--sleep", type=float, default=2.0, help="Seconds between cases (default: 2)."
    )
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

    # Resolve relative log paths → absolute so the LLM gets an unambiguous path.
    # Tool field descriptions say "Absolute path"; a ../../ string causes Claude
    # to skip tool calls and answer without reading the file.
    _log_root = str(REPO_ROOT / "services" / "ingestion" / "loghub-samples")
    for case in ev.cases:
        case["input"] = case["input"].replace(
            "../../services/ingestion/loghub-samples", _log_root
        )

    # ── DEBUG: print exactly what the agent will see and what it returns ──────
    _hdfs_log = REPO_ROOT / "services/ingestion/loghub-samples/HDFS/HDFS_2k.log"
    print(f"[DEBUG] REPO_ROOT       : {REPO_ROOT}", flush=True)
    print(f"[DEBUG] HDFS log exists : {_hdfs_log.exists()}", flush=True)
    if ev.cases:
        _sample_path = ev.cases[0]["input"].split("at: ")[1].split("\n")[0]
        print(f"[DEBUG] path in case[0] : {_sample_path}", flush=True)

    _orig_factory = ev.agent_factory

    def _debug_factory():
        agent = _orig_factory()
        _orig_run = agent.run

        def _debug_run(user_input: str) -> str:
            output = _orig_run(user_input)
            print(
                f"\n[DEBUG] agent output ({len(output)} chars):\n"
                f"{output[:800]}\n[DEBUG END]",
                flush=True,
            )
            return output

        agent.run = _debug_run
        return agent

    ev.agent_factory = _debug_factory
    # ─────────────────────────────────────────────────────────────────────────

    results = ev.run()

    total = len(results)
    passed = sum(1 for r in results if r.passed)
    failed = [r.case_id for r in results if not r.passed]
    pass_rate = passed / total if total else 0.0

    latencies = [r.latency_ms for r in results if r.latency_ms > 0]
    p95_ms = (
        sorted(latencies)[min(int(len(latencies) * 0.95), len(latencies) - 1)]
        if latencies
        else 0
    )
    avg_cost = sum(r.cost_usd for r in results) / total if total else 0.0

    payload = {
        "pass_rate": pass_rate,
        "passed": passed,
        "total": total,
        "avg_cost_usd": avg_cost,
        "p95_latency_ms": p95_ms,
        "failed": failed,
        "backend": args.backend,
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
