"""
run_multi_provider_comparison.py — Day 11: 5-model multi-provider comparison.

Runs the same 5 Day-2 eval cases against 5 OpenRouter backends:
  1. anthropic/claude-sonnet-4-6
  2. anthropic/claude-haiku-4-5
  3. openai/gpt-4o-mini
  4. mistralai/mistral-7b-instruct
  5. meta-llama/llama-3.1-70b-instruct

Captures per-case: pass/fail, latency, input/output tokens, estimated cost.
Computes: pass rate, p50/p95 latency, avg $/run, qualitative failure modes.
Writes:   experiments/multi-provider-comparison.md  (the senior-signal artifact)

Usage:
    cd agents/log-intelligence
    source .venv/bin/activate
    python run_multi_provider_comparison.py              # full run
    python run_multi_provider_comparison.py --quick      # 1 case per model (~3 min)
    python run_multi_provider_comparison.py --sleep 5    # slow down for rate limits

Requirements:
    OPENROUTER_API_KEY env var
    uv pip install -r requirements_openrouter.txt

Pricing source: https://openrouter.ai/models  (verify before publishing)
"""

from __future__ import annotations

import argparse
import json
import os
import re
import statistics
import sys
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path


# ── 5-model registry ─────────────────────────────────────────────────────────
# Pricing in USD per 1M tokens. Verify at https://openrouter.ai/models.
MODELS = [
    {
        "id": "anthropic/claude-sonnet-4-6",
        "label": "Claude Sonnet 4.6",
        "provider": "Anthropic",
        "in_usd_1m": 3.00,
        "out_usd_1m": 15.00,
        "notes": "Quality baseline. Highest cost. Best structured output adherence.",
    },
    {
        "id": "anthropic/claude-haiku-4-5",
        "label": "Claude Haiku 4.5",
        "provider": "Anthropic",
        "in_usd_1m": 0.25,
        "out_usd_1m": 1.25,
        "notes": "10× cheaper than Sonnet. Solid format adherence. First choice for dev iteration.",
    },
    {
        "id": "openai/gpt-4o-mini",
        "label": "GPT-4o Mini",
        "provider": "OpenAI",
        "in_usd_1m": 0.15,
        "out_usd_1m": 0.60,
        "notes": "Cheapest cross-provider option. Prone to header format drift.",
    },
    {
        "id": "mistralai/mistral-nemo",
        "label": "Mistral Nemo 12B",
        "provider": "Mistral AI",
        "in_usd_1m": 0.020,
        "out_usd_1m": 0.030,
        "notes": "12B open-weight model. Replaced mistral-7b-instruct (deprecated on OpenRouter May 2026). Ultra-cheap at $0.02/$0.03 per 1M tokens.",
    },
    {
        "id": "meta-llama/llama-3.1-70b-instruct",
        "label": "Llama 3.1 70B Instruct",
        "provider": "Meta (via OpenRouter)",
        "in_usd_1m": 0.52,
        "out_usd_1m": 0.75,
        "notes": "Strong open-source option. Occasionally drifts from P-level format.",
    },
]

CASES_PATH = Path("evals/cases.jsonl")
OUTPUT_PATH = (
    Path(__file__).resolve().parent / "../../experiments/multi-provider-comparison.md"
).resolve()
OUTPUTS_DIR = (
    Path(__file__).resolve().parent / "../../experiments/outputs/multi-provider"
).resolve()
DEFAULT_SLEEP = 4  # seconds between cases — avoid OpenRouter rate limits


# ── Data types ────────────────────────────────────────────────────────────────


@dataclass
class CaseResult:
    case_id: str
    passed: bool
    notes: str
    latency_ms: float
    input_tokens: int
    output_tokens: int
    output_text: str = ""

    def cost_usd(self, in_usd_1m: float, out_usd_1m: float) -> float:
        return (
            self.input_tokens / 1_000_000 * in_usd_1m
            + self.output_tokens / 1_000_000 * out_usd_1m
        )


@dataclass
class ModelRow:
    model_id: str
    label: str
    provider: str
    results: list[CaseResult] = field(default_factory=list)
    in_usd_1m: float = 0.0
    out_usd_1m: float = 0.0
    notes: str = ""

    @property
    def passed(self) -> int:
        return sum(1 for r in self.results if r.passed)

    @property
    def total(self) -> int:
        return len(self.results)

    @property
    def pass_rate_str(self) -> str:
        if not self.total:
            return "—"
        return f"{self.passed}/{self.total} ({self.passed / self.total * 100:.0f}%)"

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

    def section_count(self, section: str) -> int:
        """Count how many outputs have the required section header."""
        count = 0
        for r in self.results:
            if re.search(rf"^## {re.escape(section)}", r.output_text, re.MULTILINE):
                count += 1
        return count

    def has_log_citations(self) -> int:
        """Count outputs with actual HDFS log timestamps (evidence of deep reads)."""
        count = 0
        for r in self.results:
            if re.search(r"\b\d{6}\s+\d{6}\b", r.output_text):
                count += 1
        return count

    def p_level_compliance(self) -> int:
        """Count outputs using strict P1/P2/P3/P4 severity format."""
        count = 0
        for r in self.results:
            if re.search(r"\bP[1-4]\b", r.output_text):
                count += 1
        return count


# ── Case loading ──────────────────────────────────────────────────────────────


def load_cases(n: int | None = None) -> list[dict]:
    cases = [
        json.loads(line)
        for line in CASES_PATH.read_text().splitlines()
        if line.strip()
    ]
    return cases[:n] if n else cases


def grade(case: dict, output: str) -> tuple[bool, str]:
    rubric = case.get("rubric", "contains")
    if rubric == "contains":
        needle = case["expected"]
        ok = needle in output
        return ok, "" if ok else f"missing: {needle!r}"
    if rubric == "exact":
        ok = output.strip() == case["expected"].strip()
        return ok, "" if ok else "exact match failed"
    return False, f"unknown rubric: {rubric}"


# ── Run one model against one case ────────────────────────────────────────────


def run_case(model_id: str, case: dict) -> CaseResult:
    """Import the OpenRouter planner and run one eval case.

    cases.jsonl stores the full triage prompt in the "input" field —
    it already contains the log path, tool-use instructions, and section
    requirements. We pass it directly rather than re-constructing a prompt.
    """
    from planner_openrouter import OpenRouterPlannerConfig, OpenRouterPlanner, SYSTEM_PROMPT
    from tools_openrouter import Tools
    from memory_openrouter import Memory

    prompt = case.get("input", "")
    if not prompt:
        return CaseResult(
            case_id=case["id"],
            passed=False,
            notes="empty input in case",
            latency_ms=0,
            input_tokens=0,
            output_tokens=0,
        )

    # Fresh tools + memory per case — no state bleeds between runs
    tools = Tools()
    memory = Memory(system_prompt=SYSTEM_PROMPT)
    config = OpenRouterPlannerConfig(model=model_id)
    agent = OpenRouterPlanner(tools, memory, config)

    t0 = time.perf_counter()
    try:
        output = agent.run(prompt)
    except Exception as exc:
        return CaseResult(
            case_id=case["id"],
            passed=False,
            notes=f"exception: {exc}",
            latency_ms=(time.perf_counter() - t0) * 1000,
            input_tokens=0,
            output_tokens=0,
        )
    latency_ms = (time.perf_counter() - t0) * 1000

    passed, notes = grade(case, output)

    usage = getattr(agent, "usage", None) or {}
    return CaseResult(
        case_id=case["id"],
        passed=passed,
        notes=notes,
        latency_ms=latency_ms,
        input_tokens=usage.get("input_tokens", 0),
        output_tokens=usage.get("output_tokens", 0),
        output_text=output,
    )


# ── Write outputs ─────────────────────────────────────────────────────────────


def save_output(model_id: str, case_id: str, text: str) -> None:
    OUTPUTS_DIR.mkdir(parents=True, exist_ok=True)
    safe_model = model_id.replace("/", "-")
    path = OUTPUTS_DIR / f"{safe_model}--{case_id}.md"
    path.write_text(text, encoding="utf-8")


# ── Markdown report ───────────────────────────────────────────────────────────


def build_report(rows: list[ModelRow], run_date: str, quick: bool) -> str:
    cases_note = "1 case (--quick smoke test)" if quick else "5 eval cases"

    lines = [
        "# Multi-Provider Comparison — Log Triage Agent",
        "",
        f"> Generated: {run_date}  |  Eval: {cases_note}  |  Agent: Day-2 log triage  |  Log: HDFS_2k.log",
        ">",
        "> **Why this matters:** Provider choice is an engineering decision with measurable cost, quality, and latency trade-offs.",
        "> This experiment gives you real numbers — not opinions — for a structured log triage task.",
        "",
        "---",
        "",
        "## Summary table",
        "",
        "| Model | Provider | Pass rate | p50 latency | p95 latency | Avg $/run | Sections present | P-level format | Log citations |",
        "|---|---|---|---|---|---|---|---|---|",
    ]

    for row in rows:
        sections = f"{row.section_count('Severity')}/{row.total} Severity, {row.section_count('Root Cause Hypothesis')}/{row.total} RCH, {row.section_count('Suggested Actions')}/{row.total} SA"
        p_fmt = f"{row.p_level_compliance()}/{row.total}"
        citations = f"{row.has_log_citations()}/{row.total}"
        lines.append(
            f"| **{row.label}** | {row.provider} "
            f"| {row.pass_rate_str} "
            f"| {row.p50_ms / 1000:.1f}s "
            f"| {row.p95_ms / 1000:.1f}s "
            f"| ${row.avg_cost_usd:.4f} "
            f"| {sections} "
            f"| {p_fmt} "
            f"| {citations} |"
        )

    lines += [
        "",
        "> **Sections present:** `## Severity`, `## Root Cause Hypothesis`, `## Suggested Actions` — all 3 required.",
        "> **P-level format:** Must use `P1`/`P2`/`P3`/`P4` — not `High`/`Low`/`Critical`.",
        "> **Log citations:** At least one HDFS timestamp in `## Root Cause Hypothesis` — proves the model read the log.",
        "",
        "---",
        "",
        "## Per-model results",
        "",
    ]

    for row in rows:
        lines += [
            f"### {row.label}  (`{row.model_id}`)",
            "",
            f"**Provider:** {row.provider}  |  **Pass rate:** {row.pass_rate_str}  |  **Avg $/run:** ${row.avg_cost_usd:.4f}",
            "",
            "| Case | Pass | Latency | Input tokens | Output tokens | Notes |",
            "|---|---|---|---|---|---|",
        ]
        for r in row.results:
            icon = "✅" if r.passed else "❌"
            lines.append(
                f"| {r.case_id} | {icon} | {r.latency_ms / 1000:.1f}s "
                f"| {r.input_tokens:,} | {r.output_tokens:,} | {r.notes or '—'} |"
            )

        lines += [
            "",
            f"**Total tokens:** {row.total_input_tokens:,} in / {row.total_output_tokens:,} out  "
            f"|  **p50:** {row.p50_ms / 1000:.1f}s  |  **p95:** {row.p95_ms / 1000:.1f}s",
            "",
            f"**Notes:** {row.notes}",
            "",
        ]

    # ── Qualitative observations (to be filled in after reviewing outputs) ────
    lines += [
        "---",
        "",
        "## Qualitative observations",
        "",
        "> **Instructions:** After running the experiment, open `experiments/outputs/multi-provider/`",
        "> and read each model's full triage output. Fill in the table below.",
        "",
        "| Model | Output quality | Structured format | Notable failure modes |",
        "|---|---|---|---|",
    ]
    for row in rows:
        lines.append(f"| **{row.label}** | — | — | — |")

    lines += [
        "",
        "> Quality scale: **Excellent** / **Good** / **Acceptable** / **Poor**",
        "> Format: **Yes** / **Partial** (note which sections failed) / **No**",
        "",
        "---",
        "",
        "## Recommendation",
        "",
        "> **Fill this in after reviewing the qualitative observations above.**",
        "",
        "**Production (quality-sensitive, on-call SRE reads this):**",
        "→ TODO — e.g., `anthropic/claude-sonnet-4-6` because ...",
        "",
        "**Dev iteration (cost-optimised, you're tuning prompts):**",
        "→ TODO — e.g., `anthropic/claude-haiku-4-5` because ...",
        "",
        "**Routing strategy:**",
        "→ TODO — e.g., \"Run Haiku on all logs; if severity is P1/P2, re-run with Sonnet for a second opinion.\"",
        "",
        "---",
        "",
        "## Failure mode taxonomy",
        "",
        "Failure modes observed across all 5 models during this experiment:",
        "",
        "| Failure mode | How to detect | Models affected |",
        "|---|---|---|",
        "| Missing sections | `grep -c \"^## \" output.md` < 3 | — |",
        "| Header format drift | Uses `# Severity` or `**Severity**` instead of `## Severity` | — |",
        "| No log citations | No HDFS timestamps in Root Cause Hypothesis | — |",
        "| Generic actions | \"Check the logs\" / \"restart the service\" — no specifics | — |",
        "| Severity label non-standard | Uses `High`/`Low` instead of `P1`–`P4` | — |",
        "| Skipped tool calls | Low input token count; no `read_log_chunk` calls evident | — |",
        "| Truncated output | Report cuts off mid-sentence | — |",
        "",
        "> Fill in the **Models affected** column after reviewing outputs.",
        "",
        "---",
        "",
        "## Pricing reference",
        "",
        "Prices in USD per 1M tokens. Verify at https://openrouter.ai/models before citing.",
        "",
        "| Model | Input $/1M | Output $/1M |",
        "|---|---|---|",
    ]

    for m in MODELS:
        lines.append(
            f"| `{m['id']}` | ${m['in_usd_1m']:.2f} | ${m['out_usd_1m']:.2f} |"
        )

    lines += [
        "",
        "---",
        "",
        f"*Report generated by `run_multi_provider_comparison.py` — {run_date}*",
    ]

    return "\n".join(lines)


# ── Main ──────────────────────────────────────────────────────────────────────


def main() -> None:
    parser = argparse.ArgumentParser(description="Multi-provider log triage comparison")
    parser.add_argument("--quick", action="store_true", help="Run 1 case per model (smoke test)")
    parser.add_argument("--sleep", type=float, default=DEFAULT_SLEEP, help="Seconds between cases")
    parser.add_argument("--model", help="Run only this model ID (for partial reruns)")
    args = parser.parse_args()

    if not os.getenv("OPENROUTER_API_KEY"):
        print("ERROR: OPENROUTER_API_KEY not set", file=sys.stderr)
        sys.exit(1)

    n_cases = 1 if args.quick else None
    cases = load_cases(n_cases)
    models_to_run = [m for m in MODELS if not args.model or m["id"] == args.model]

    print(f"\n🔬  Multi-Provider Comparison — {len(cases)} case(s) × {len(models_to_run)} model(s)\n")

    rows: list[ModelRow] = []

    for m in models_to_run:
        row = ModelRow(
            model_id=m["id"],
            label=m["label"],
            provider=m["provider"],
            in_usd_1m=m["in_usd_1m"],
            out_usd_1m=m["out_usd_1m"],
            notes=m["notes"],
        )
        rows.append(row)

        print(f"▶  {m['label']}  ({m['id']})")
        for i, case in enumerate(cases):
            result = run_case(m["id"], case)
            row.results.append(result)

            icon = "✓" if result.passed else "✗"
            print(
                f"    [{i + 1}/{len(cases)}] {case['id']} ... {icon}  "
                f"{result.latency_ms / 1000:.1f}s  "
                f"in={result.input_tokens} out={result.output_tokens}"
            )
            if result.notes:
                print(f"           note: {result.notes}")

            # Save full output for qualitative review
            if result.output_text:
                save_output(m["id"], case["id"], result.output_text)

            if i < len(cases) - 1:
                time.sleep(args.sleep)

        print(
            f"    → {row.pass_rate_str}  |  p50={row.p50_ms / 1000:.1f}s  "
            f"|  avg=${row.avg_cost_usd:.4f}/run\n"
        )

        # Sleep between models to avoid rate limits
        if m != models_to_run[-1]:
            print(f"   (sleeping {args.sleep * 2:.0f}s before next model…)")
            time.sleep(args.sleep * 2)

    # ── Write report ──────────────────────────────────────────────────────────
    run_date = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    report = build_report(rows, run_date, args.quick)
    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_PATH.write_text(report, encoding="utf-8")

    print(f"✅  Report written to: {OUTPUT_PATH}")
    print(f"    Outputs saved to:  {OUTPUTS_DIR}")
    print(f"\n    Next: open the outputs and fill in qualitative observations.")
    print(f"    Then update the Recommendation section in the report.")


if __name__ == "__main__":
    main()
