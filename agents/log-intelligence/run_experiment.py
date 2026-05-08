"""
run_experiment.py — Day 3: multi-model routing experiment.

Runs the 5 eval cases against three OpenRouter models, captures latency
and token usage per case, computes p50/p95 latency and estimated $/run,
then writes a Markdown comparison report.

Usage (from log-intelligence/):
    python run_experiment.py                  # full run — all 3 models × 5 cases
    python run_experiment.py --quick          # smoke test — 1 case per model
    python run_experiment.py --sleep 3        # override sleep between cases (default: 3s)

Output:
    aiops-platform/experiments/log-triage-model-routing.md

Requires:
    OPENROUTER_API_KEY env var
    uv pip install -r requirements_openrouter.txt

MODELS TO COMPARE:
  anthropic/claude-sonnet-4-6   — quality baseline (most expensive)
  anthropic/claude-haiku-4-5    — cheap Anthropic (10× cheaper than Sonnet)
  openai/gpt-4o-mini            — cheap cross-provider alternative

Pricing source: https://openrouter.ai/models (verify before publishing results)
"""
from __future__ import annotations

import argparse
import json
import os
import statistics
import sys
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path


# ── Model registry with pricing (USD / 1M tokens) ────────────────────────────
# Verify current prices at https://openrouter.ai/models before publishing results.
MODELS = [
    {
        "id":         "anthropic/claude-sonnet-4-6",
        "label":      "Claude Sonnet 4.6",
        "in_usd_1m":  3.00,
        "out_usd_1m": 15.00,
    },
    {
        "id":         "anthropic/claude-haiku-4-5",
        "label":      "Claude Haiku 4.5",
        "in_usd_1m":  0.25,
        "out_usd_1m": 1.25,
    },
    {
        "id":         "openai/gpt-4o-mini",
        "label":      "GPT-4o Mini",
        "in_usd_1m":  0.15,
        "out_usd_1m": 0.60,
    },
]

CASES_PATH   = Path("evals/cases.jsonl")
OUTPUT_PATH  = (Path(__file__).resolve().parent / "../../experiments/log-triage-model-routing.md").resolve()
OUTPUTS_DIR  = (Path(__file__).resolve().parent / "../../experiments/outputs").resolve()
DEFAULT_SLEEP = 3   # seconds between cases — avoids OpenRouter rate limits


# ── Data types ────────────────────────────────────────────────────────────────

@dataclass
class CaseResult:
    case_id:       str
    passed:        bool
    notes:         str
    latency_ms:    float
    input_tokens:  int
    output_tokens: int

    def cost_usd(self, in_usd_1m: float, out_usd_1m: float) -> float:
        return (self.input_tokens  / 1_000_000 * in_usd_1m +
                self.output_tokens / 1_000_000 * out_usd_1m)


@dataclass
class ModelRow:
    model_id:   str
    label:      str
    results:    list[CaseResult] = field(default_factory=list)
    in_usd_1m:  float = 0.0
    out_usd_1m: float = 0.0

    @property
    def passed(self) -> int:
        return sum(1 for r in self.results if r.passed)

    @property
    def total(self) -> int:
        return len(self.results)

    @property
    def pass_rate(self) -> str:
        if not self.total:
            return "—"
        return f"{self.passed}/{self.total} ({self.passed/self.total*100:.0f}%)"

    @property
    def latencies(self) -> list[float]:
        return [r.latency_ms for r in self.results if r.latency_ms > 0]

    @property
    def p50_ms(self) -> float:
        return statistics.median(self.latencies) if self.latencies else 0.0

    @property
    def p95_ms(self) -> float:
        s = sorted(self.latencies)
        return s[min(int(len(s) * 0.95), len(s) - 1)] if s else 0.0

    @property
    def avg_cost_usd(self) -> float:
        if not self.results:
            return 0.0
        return sum(r.cost_usd(self.in_usd_1m, self.out_usd_1m) for r in self.results) / len(self.results)

    @property
    def total_input_tokens(self) -> int:
        return sum(r.input_tokens for r in self.results)

    @property
    def total_output_tokens(self) -> int:
        return sum(r.output_tokens for r in self.results)


# ── Case loading & grading ────────────────────────────────────────────────────

def load_cases(n: int | None = None) -> list[dict]:
    cases = [json.loads(line) for line in CASES_PATH.read_text().splitlines() if line.strip()]
    return cases[:n] if n else cases


def grade(case: dict, output: str) -> tuple[bool, str]:
    rubric = case.get("rubric", "contains")
    if rubric == "contains":
        needle = case["expected"]
        ok = needle in output
        return ok, "" if ok else f"missing: {needle!r}"
    if rubric == "exact":
        ok = output.strip() == case["expected"]
        return ok, "" if ok else f"expected {case['expected']!r}"
    return True, "(llm-judge stub)"


# ── Per-model runner ──────────────────────────────────────────────────────────

def run_model(model: dict, cases: list[dict], sleep_sec: float) -> tuple[list[CaseResult], dict[str, str]]:
    """Run all cases for one model.

    Returns:
        results    — list of CaseResult (quantitative metrics)
        outputs    — dict mapping case_id → full triage text (for qualitative review)
    """
    from planner_openrouter import OpenRouterPlanner, OpenRouterPlannerConfig, SYSTEM_PROMPT
    from tools_openrouter import Tools
    from memory_openrouter import Memory

    results: list[CaseResult] = []
    outputs: dict[str, str]   = {}

    for i, case in enumerate(cases, 1):
        print(f"    [{i}/{len(cases)}] {case['id']} ...", end=" ", flush=True)

        cfg   = OpenRouterPlannerConfig(model=model["id"])
        agent = OpenRouterPlanner(
            tools=Tools(),
            memory=Memory(system_prompt=SYSTEM_PROMPT),
            config=cfg,
        )
        t0 = time.perf_counter()
        try:
            output    = agent.run(case["input"])
            latency_ms = (time.perf_counter() - t0) * 1000
            passed, notes = grade(case, output)
        except Exception as exc:
            latency_ms = (time.perf_counter() - t0) * 1000
            output = f"ERROR: {exc}"
            passed, notes = False, str(exc)[:120]
            agent.usage = {"input_tokens": 0, "output_tokens": 0}

        usage = getattr(agent, "usage", {"input_tokens": 0, "output_tokens": 0})
        results.append(CaseResult(
            case_id=case["id"],
            passed=passed,
            notes=notes,
            latency_ms=latency_ms,
            input_tokens=usage.get("input_tokens", 0),
            output_tokens=usage.get("output_tokens", 0),
        ))
        outputs[case["id"]] = output   # ← save full text for qualitative review

        mark = "✓" if passed else "✗"
        print(f"{mark}  {latency_ms/1000:.1f}s  "
              f"in={usage.get('input_tokens',0)} out={usage.get('output_tokens',0)}")

        if i < len(cases):
            time.sleep(sleep_sec)

    return results, outputs


def _model_slug(model_id: str) -> str:
    """'anthropic/claude-haiku-4-5' → 'anthropic-claude-haiku-4-5'"""
    return model_id.replace("/", "-")


def save_outputs(model: dict, outputs: dict[str, str]) -> None:
    """Write all triage outputs for one model to experiments/outputs/<slug>.md."""
    OUTPUTS_DIR.mkdir(parents=True, exist_ok=True)
    slug = _model_slug(model["id"])
    path = OUTPUTS_DIR / f"{slug}.md"

    lines = [
        f"# Triage Outputs — {model['label']}",
        "",
        f"> Model: `{model['id']}`  ",
        "> Generated by `run_experiment.py`  ",
        "",
        "---",
        "",
    ]
    for case_id, text in outputs.items():
        lines += [
            f"## Case: {case_id}",
            "",
            text.strip(),
            "",
            "---",
            "",
        ]
    path.write_text("\n".join(lines))
    print(f"   → outputs saved: {path}")


# ── Markdown report ───────────────────────────────────────────────────────────

def render_report(rows: list[ModelRow], run_date: str, n_cases: int) -> str:
    lines = [
        "# Log Triage — Model Routing Experiment",
        "",
        f"> **Run date:** {run_date}  ",
        "> **Agent:** `log-intelligence` · **Log:** `HDFS_2k.log` (2 000 lines)  ",
        f"> **Eval cases:** {n_cases} labeled cases (rubric: `contains`)  ",
        "> **Pricing:** verify current rates at [openrouter.ai/models](https://openrouter.ai/models)",
        "",
        "## Summary",
        "",
        "| Model | Pass rate | p50 latency | p95 latency | Avg $/run |",
        "|---|---|---|---|---|",
    ]
    for row in rows:
        lines.append(
            f"| {row.label} (`{row.model_id}`) "
            f"| {row.pass_rate} "
            f"| {row.p50_ms:.0f} ms "
            f"| {row.p95_ms:.0f} ms "
            f"| ${row.avg_cost_usd:.4f} |"
        )

    lines += ["", "## Case-by-case breakdown", ""]
    for row in rows:
        lines.append(f"### {row.label}")
        lines.append("")
        lines.append("| Case | Result | Latency | Input tok | Output tok | Cost |")
        lines.append("|---|---|---|---|---|---|")
        for r in row.results:
            mark  = "✅ PASS" if r.passed else "❌ FAIL"
            extra = f" — {r.notes}" if r.notes and not r.passed else ""
            cost  = r.cost_usd(row.in_usd_1m, row.out_usd_1m)
            lines.append(
                f"| {r.case_id} | {mark}{extra} "
                f"| {r.latency_ms:.0f} ms "
                f"| {r.input_tokens} | {r.output_tokens} "
                f"| ${cost:.4f} |"
            )
        lines.append(
            f"| **Total** | **{row.passed}/{row.total}** | — "
            f"| **{row.total_input_tokens}** | **{row.total_output_tokens}** "
            f"| **${sum(r.cost_usd(row.in_usd_1m, row.out_usd_1m) for r in row.results):.4f}** |"
        )
        lines.append("")

    lines += [
        "## Qualitative observations",
        "",
        "<!-- Fill in after reviewing the outputs from each model. -->",
        "",
    ]
    for row in rows:
        lines += [
            f"**{row.label}:** ",
            "",
            "- Output quality: _TODO_",
            "- Followed structured output format: _TODO_",
            "- Notable failure modes: _TODO_",
            "",
        ]

    lines += [
        "## Recommendation",
        "",
        "<!-- Fill in based on the numbers above. -->",
        "",
        "**For production log triage:** _TODO — which model, why_  ",
        "**For development iteration (cost-optimised):** _TODO — which model, why_  ",
        "**Routing strategy:** _TODO — e.g. 'Haiku for initial triage, Sonnet only when P1/P2 detected'_  ",
        "",
        "---",
        "",
        f"_Generated by `run_experiment.py` · {run_date}_",
    ]
    return "\n".join(lines)


# ── Entry point ───────────────────────────────────────────────────────────────

def main() -> int:
    parser = argparse.ArgumentParser(
        description="Day 3 — multi-model routing experiment for log-intelligence agent.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "examples:\n"
            "  python run_experiment.py            # full run\n"
            "  python run_experiment.py --quick    # 1 case per model (smoke test)\n"
            "  python run_experiment.py --sleep 5  # slower — avoids free-tier rate limits\n"
        ),
    )
    parser.add_argument("--quick",  action="store_true", help="Run 1 case per model instead of all 5.")
    parser.add_argument("--sleep",  type=float, default=DEFAULT_SLEEP,
                        help=f"Seconds to sleep between cases (default: {DEFAULT_SLEEP}).")
    args = parser.parse_args()

    if not os.environ.get("OPENROUTER_API_KEY"):
        print("ERROR: OPENROUTER_API_KEY not set.", file=sys.stderr)
        return 1

    n_cases  = 1 if args.quick else None
    cases    = load_cases(n_cases)
    run_date = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")

    print(f"\n{'='*60}")
    print("  Log Triage — Model Routing Experiment")
    print(f"  {len(cases)} case(s) × {len(MODELS)} model(s)")
    print(f"  {run_date}")
    print(f"{'='*60}")

    all_rows: list[ModelRow] = []
    for model in MODELS:
        print(f"\n▶  {model['label']}  ({model['id']})")
        results, outputs = run_model(model, cases, sleep_sec=args.sleep)
        row = ModelRow(
            model_id=model["id"],
            label=model["label"],
            results=results,
            in_usd_1m=model["in_usd_1m"],
            out_usd_1m=model["out_usd_1m"],
        )
        all_rows.append(row)
        save_outputs(model, outputs)   # ← write triage text to experiments/outputs/
        print(f"   → {row.pass_rate}  p50={row.p50_ms:.0f}ms  p95={row.p95_ms:.0f}ms  "
              f"avg_cost=${row.avg_cost_usd:.4f}/run")

    # Write quantitative report
    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    report = render_report(all_rows, run_date, len(cases))
    OUTPUT_PATH.write_text(report)

    print(f"\n{'='*60}")
    print("✅  Quantitative report:")
    print(f"    {OUTPUT_PATH}")
    print("\n✅  Triage outputs for qualitative review:")
    for model in MODELS:
        slug = _model_slug(model["id"])
        print(f"    {OUTPUTS_DIR}/{slug}.md")
    print("\nNext steps:")
    print("  1. Open each file in experiments/outputs/ and review triage quality")
    print("  2. Fill in 'Qualitative observations' in the report")
    print("  3. Fill in the 'Recommendation' section with your routing decision")
    print("  4. git add experiments/ && git commit")
    print(f"{'='*60}\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
