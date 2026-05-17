"""
evals/run_routing_experiment.py — Day 7: K8s Doctor model routing experiment.

Runs all 5 eval cases twice:
  1. ROUTING ON  — observe: claude-haiku-4-5, hypothesize/propose: claude-sonnet-4-6
  2. ROUTING OFF — all nodes: claude-sonnet-4-6 (baseline, max quality, max cost)

Captures latency and estimated cost per run, then writes a comparison
report to experiments/k8s-doctor-model-routing.md.

USAGE (from agents/k8s-doctor/)
────────────────────────────────
    python evals/run_routing_experiment.py
    python evals/run_routing_experiment.py --quick      # 1 case per strategy
    python evals/run_routing_experiment.py --sleep 5    # slow down between calls

OUTPUT
──────
    aiops-platform/experiments/k8s-doctor-model-routing.md

COST ESTIMATE
─────────────
Routing ON  (~3 calls: haiku observe + 2× sonnet reason):  ≈ $0.003/run × 5 = $0.015
Routing OFF (~3 calls: all sonnet):                          ≈ $0.012/run × 5 = $0.060
Total experiment cost: ≈ $0.075

Pricing reference (May 2026 — verify at https://www.anthropic.com/pricing):
  claude-haiku-4-5-20251001: $0.25 in / $1.25 out per 1M tokens
  claude-sonnet-4-6:          $3.00 in / $15.00 out per 1M tokens
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
import unittest.mock as mock
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from statistics import mean, median

# Ensure src/ is importable
sys.path.insert(0, str(Path(__file__).parent.parent))

from dotenv import load_dotenv
load_dotenv(Path(__file__).parent.parent / ".env")

CASES_PATH = Path(__file__).parent / "cases.jsonl"
OUTPUT_PATH = (
    Path(__file__).resolve().parent.parent / "../../experiments/k8s-doctor-model-routing.md"
).resolve()

# ── Pricing (USD / 1M tokens) — verify at anthropic.com/pricing ──────────────
HAIKU_IN_USD_1M  = 0.25
HAIKU_OUT_USD_1M = 1.25
SONNET_IN_USD_1M  = 3.00
SONNET_OUT_USD_1M = 15.00

# Rough token estimates per node (actual varies by output length)
# Observe  : ~800 in, ~300 out  (kubectl dump + signal extraction)
# Hypothesize: ~600 in, ~400 out
# Propose  : ~900 in, ~600 out
OBSERVE_IN_TOKENS    = 800
OBSERVE_OUT_TOKENS   = 300
HYPOTHESIZE_IN_TOKENS = 600
HYPOTHESIZE_OUT_TOKENS = 400
PROPOSE_IN_TOKENS    = 900
PROPOSE_OUT_TOKENS   = 600


def estimate_cost(routing_on: bool) -> float:
    """Estimate $/run based on token estimates and model pricing."""
    if routing_on:
        # haiku for observe, sonnet for hypothesize + propose
        observe_cost = (
            OBSERVE_IN_TOKENS / 1_000_000 * HAIKU_IN_USD_1M
            + OBSERVE_OUT_TOKENS / 1_000_000 * HAIKU_OUT_USD_1M
        )
        reason_cost = (
            (HYPOTHESIZE_IN_TOKENS + PROPOSE_IN_TOKENS) / 1_000_000 * SONNET_IN_USD_1M
            + (HYPOTHESIZE_OUT_TOKENS + PROPOSE_OUT_TOKENS) / 1_000_000 * SONNET_OUT_USD_1M
        )
        return observe_cost + reason_cost
    else:
        # all sonnet
        total_in = OBSERVE_IN_TOKENS + HYPOTHESIZE_IN_TOKENS + PROPOSE_IN_TOKENS
        total_out = OBSERVE_OUT_TOKENS + HYPOTHESIZE_OUT_TOKENS + PROPOSE_OUT_TOKENS
        return (
            total_in / 1_000_000 * SONNET_IN_USD_1M
            + total_out / 1_000_000 * SONNET_OUT_USD_1M
        )


@dataclass
class CaseResult:
    case_id: str
    passed: bool
    latency_ms: float
    missing_keywords: list[str] = field(default_factory=list)
    error: str = ""


@dataclass
class StrategyResult:
    strategy: str
    observe_model: str
    reason_model: str
    results: list[CaseResult] = field(default_factory=list)

    @property
    def pass_rate(self) -> float:
        if not self.results:
            return 0.0
        return sum(1 for r in self.results if r.passed) / len(self.results)

    @property
    def avg_latency_ms(self) -> float:
        if not self.results:
            return 0.0
        return mean(r.latency_ms for r in self.results)

    @property
    def p50_latency_ms(self) -> float:
        if not self.results:
            return 0.0
        return median(r.latency_ms for r in self.results)

    @property
    def estimated_cost_per_run(self) -> float:
        return estimate_cost(self.strategy == "routing_on")

    @property
    def total_estimated_cost(self) -> float:
        return self.estimated_cost_per_run * len(self.results)


def load_cases(quick: bool = False) -> list[dict]:
    cases = []
    with open(CASES_PATH) as f:
        for line in f:
            line = line.strip()
            if line:
                cases.append(json.loads(line))
    if quick:
        cases = cases[:1]
    return cases


def run_strategy(
    cases: list[dict],
    observe_model: str,
    reason_model: str,
    strategy_name: str,
    sleep_s: float = 2.0,
) -> StrategyResult:
    """Run all cases with the given model configuration."""
    os.environ["OBSERVE_MODEL"] = observe_model
    os.environ["REASON_MODEL"] = reason_model

    # Re-import nodes to pick up new env vars
    # (they read OBSERVE_MODEL / REASON_MODEL at import time)
    import importlib
    import src.graph.nodes as nodes_module
    importlib.reload(nodes_module)

    from src.graph.graph import build_graph
    graph = build_graph()

    from src.graph.state import initial_state

    strategy = StrategyResult(
        strategy=strategy_name,
        observe_model=observe_model,
        reason_model=reason_model,
    )

    for i, case in enumerate(cases):
        if i > 0:
            time.sleep(sleep_s)

        fixtures = case["fixtures"]

        patches = [
            mock.patch.object(nodes_module, "kubectl_get_pods", return_value=fixtures["pods"]),
            mock.patch.object(nodes_module, "kubectl_describe", return_value=fixtures["describe"]),
            mock.patch.object(
                nodes_module, "kubectl_logs",
                side_effect=lambda res, ns, **kw: (
                    fixtures["prev_logs"] if kw.get("previous") else fixtures["logs"]
                ),
            ),
            mock.patch.object(nodes_module, "kubectl_events", return_value=fixtures["events"]),
            mock.patch.object(nodes_module, "prom_query", return_value=fixtures["prom_up"]),
        ]

        state = initial_state(
            symptom=case["symptom"],
            namespace=case["namespace"],
            resource=case["resource"],
        )

        start = time.time()
        with patches[0], patches[1], patches[2], patches[3], patches[4]:
            try:
                result = graph.invoke(state)
                latency_ms = (time.time() - start) * 1000
                diagnosis = result.get("final_diagnosis", "")
                diagnosis_lower = diagnosis.lower()
                missing = [kw for kw in case["expected_keywords"] if kw.lower() not in diagnosis_lower]
                passed = len(missing) == 0
                strategy.results.append(CaseResult(
                    case_id=case["id"],
                    passed=passed,
                    latency_ms=latency_ms,
                    missing_keywords=missing,
                ))
            except Exception as exc:
                latency_ms = (time.time() - start) * 1000
                strategy.results.append(CaseResult(
                    case_id=case["id"],
                    passed=False,
                    latency_ms=latency_ms,
                    error=str(exc),
                ))

        icon = "✅" if strategy.results[-1].passed else "❌"
        print(
            f"    {icon} {case['id']}  {strategy.results[-1].latency_ms / 1000:.1f}s",
            flush=True,
        )

    return strategy


def write_report(
    routing_on: StrategyResult,
    routing_off: StrategyResult,
    output_path: Path,
) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)

    latency_delta_ms = routing_on.avg_latency_ms - routing_off.avg_latency_ms
    cost_savings_pct = (
        (routing_off.estimated_cost_per_run - routing_on.estimated_cost_per_run)
        / routing_off.estimated_cost_per_run * 100
        if routing_off.estimated_cost_per_run > 0 else 0
    )

    now = datetime.now(tz=timezone.utc).strftime("%Y-%m-%d")

    lines = [
        "# K8s Doctor — Model Routing Experiment",
        "",
        f"> Generated: {now}  ",
        f"> Cases: {len(routing_on.results)} | Eval set: `evals/cases.jsonl`  ",
        "> Cost estimates based on token averages — cross-check with LangSmith for actuals.",
        "",
        "## Routing strategies compared",
        "",
        "| Strategy | observe node | hypothesize node | propose node |",
        "|---|---|---|---|",
        f"| **Routing ON** | `claude-haiku-4-5` | `claude-sonnet-4-6` | `claude-sonnet-4-6` |",
        f"| **Routing OFF** | `claude-sonnet-4-6` | `claude-sonnet-4-6` | `claude-sonnet-4-6` |",
        "",
        "**Rationale:** `observe` runs read-only kubectl commands and extracts signals —",
        "a cheap, deterministic task. `hypothesize` and `propose` require complex reasoning",
        "over ambiguous data — the task where Sonnet's quality advantage shows.",
        "",
        "## Results summary",
        "",
        "| Metric | Routing ON | Routing OFF | Delta |",
        "|---|---|---|---|",
        f"| Pass rate | {routing_on.pass_rate * 100:.0f}% ({sum(r.passed for r in routing_on.results)}/{len(routing_on.results)}) | {routing_off.pass_rate * 100:.0f}% ({sum(r.passed for r in routing_off.results)}/{len(routing_off.results)}) | {(routing_on.pass_rate - routing_off.pass_rate) * 100:+.0f}pp |",
        f"| Avg latency | {routing_on.avg_latency_ms / 1000:.1f}s | {routing_off.avg_latency_ms / 1000:.1f}s | {latency_delta_ms / 1000:+.1f}s |",
        f"| p50 latency | {routing_on.p50_latency_ms / 1000:.1f}s | {routing_off.p50_latency_ms / 1000:.1f}s | — |",
        f"| Est. $/run | ${routing_on.estimated_cost_per_run:.4f} | ${routing_off.estimated_cost_per_run:.4f} | {cost_savings_pct:.0f}% cheaper |",
        f"| Est. $/5 cases | ${routing_on.total_estimated_cost:.3f} | ${routing_off.total_estimated_cost:.3f} | — |",
        "",
        "## Per-case breakdown",
        "",
        "### Routing ON",
        "",
        "| Case | Pass | Latency | Notes |",
        "|---|---|---|---|",
    ]

    for r in routing_on.results:
        icon = "✅" if r.passed else "❌"
        notes = ", ".join(r.missing_keywords) if r.missing_keywords else (r.error or "—")
        lines.append(f"| {r.case_id} | {icon} | {r.latency_ms / 1000:.1f}s | {notes} |")

    lines += [
        "",
        "### Routing OFF (all Sonnet)",
        "",
        "| Case | Pass | Latency | Notes |",
        "|---|---|---|---|",
    ]

    for r in routing_off.results:
        icon = "✅" if r.passed else "❌"
        notes = ", ".join(r.missing_keywords) if r.missing_keywords else (r.error or "—")
        lines.append(f"| {r.case_id} | {icon} | {r.latency_ms / 1000:.1f}s | {notes} |")

    lines += [
        "",
        "## Qualitative observations",
        "",
        "### Routing ON (haiku observe + sonnet reason)",
        "",
        "<!-- Fill in after reviewing diagnosis outputs -->",
        "- Output quality: (Excellent / Good / Acceptable / Poor)",
        "- Root cause accuracy: (correct / partial / wrong) — note which cases",
        "- Remediation specificity: (specific kubectl commands / generic / missing)",
        "- Notable failure modes: (list, or 'None observed')",
        "",
        "### Routing OFF (all Sonnet)",
        "",
        "<!-- Fill in after reviewing diagnosis outputs -->",
        "- Output quality: (Excellent / Good / Acceptable / Poor)",
        "- Root cause accuracy: (correct / partial / wrong)",
        "- Remediation specificity:",
        "- Notable failure modes:",
        "",
        "## Recommendation",
        "",
        "<!-- Fill in based on your observations -->",
        "",
        "**Production (on-call SRE relies on this):** [Routing ON / OFF] — [reason]",
        "",
        "**Development / prompt tuning:** [Routing ON — cost-optimized] — reason: observe",
        "node uses haiku for raw signal extraction which doesn't require high reasoning",
        "quality; only the hypothesis and remediation nodes benefit from Sonnet.",
        "",
        f"**Estimated savings at scale:** If the agent runs 100×/day:",
        f"  - Routing ON:  ${routing_on.estimated_cost_per_run * 100:.2f}/day",
        f"  - Routing OFF: ${routing_off.estimated_cost_per_run * 100:.2f}/day",
        f"  - Saving: ${(routing_off.estimated_cost_per_run - routing_on.estimated_cost_per_run) * 100:.2f}/day  "
        f"(${(routing_off.estimated_cost_per_run - routing_on.estimated_cost_per_run) * 36500:.0f}/year)",
        "",
        "## How to reproduce",
        "",
        "```bash",
        "cd agents/k8s-doctor",
        "",
        "# Full experiment (both strategies × 5 cases)",
        "python evals/run_routing_experiment.py",
        "",
        "# Quick smoke test (1 case each)",
        "python evals/run_routing_experiment.py --quick",
        "",
        "# Run eval with routing ON manually",
        "OBSERVE_MODEL=claude-haiku-4-5-20251001 REASON_MODEL=claude-sonnet-4-6 \\",
        "  python evals/run_eval.py",
        "",
        "# Run eval with routing OFF (all Sonnet)",
        "OBSERVE_MODEL=claude-sonnet-4-6 REASON_MODEL=claude-sonnet-4-6 \\",
        "  python evals/run_eval.py",
        "```",
    ]

    output_path.write_text("\n".join(lines) + "\n")
    print(f"\n✅ Report written to: {output_path}")


def main() -> None:
    p = argparse.ArgumentParser(
        description="K8s Doctor model routing experiment",
    )
    p.add_argument("--quick", action="store_true", help="Run 1 case per strategy (smoke test)")
    p.add_argument("--sleep", type=float, default=2.0, help="Seconds between cases (default: 2)")
    args = p.parse_args()

    print("\nK8s Doctor — Model Routing Experiment")
    print(f"  Cases file : {CASES_PATH}")
    print(f"  Output     : {OUTPUT_PATH}")
    print(f"  Mode       : {'QUICK (1 case)' if args.quick else 'FULL (5 cases)'}")
    print()

    cases = load_cases(quick=args.quick)

    # ── Strategy 1: Routing ON ─────────────────────────────────────────────────
    print("▶ Strategy 1: ROUTING ON (haiku observe + sonnet reason)")
    routing_on = run_strategy(
        cases,
        observe_model="claude-haiku-4-5-20251001",
        reason_model="claude-sonnet-4-6",
        strategy_name="routing_on",
        sleep_s=args.sleep,
    )
    print(
        f"  Pass rate: {routing_on.pass_rate * 100:.0f}%  "
        f"Avg latency: {routing_on.avg_latency_ms / 1000:.1f}s  "
        f"Est. $/run: ${routing_on.estimated_cost_per_run:.4f}"
    )
    print()

    # ── Strategy 2: Routing OFF ────────────────────────────────────────────────
    print("▶ Strategy 2: ROUTING OFF (all Sonnet)")
    routing_off = run_strategy(
        cases,
        observe_model="claude-sonnet-4-6",
        reason_model="claude-sonnet-4-6",
        strategy_name="routing_off",
        sleep_s=args.sleep,
    )
    print(
        f"  Pass rate: {routing_off.pass_rate * 100:.0f}%  "
        f"Avg latency: {routing_off.avg_latency_ms / 1000:.1f}s  "
        f"Est. $/run: ${routing_off.estimated_cost_per_run:.4f}"
    )
    print()

    write_report(routing_on, routing_off, OUTPUT_PATH)


if __name__ == "__main__":
    main()
