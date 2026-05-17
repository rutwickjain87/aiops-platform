"""
evals/run_eval.py — K8s Doctor offline eval runner.

Runs 5 pre-defined diagnostic cases with canned kubectl/Prometheus fixture
data (no live cluster required). Each case patches the tool functions so
the graph receives realistic raw inputs, then checks that the final
diagnosis contains all expected keywords.

USAGE
─────
    # From agents/k8s-doctor/
    python evals/run_eval.py                        # run all 5 cases
    python evals/run_eval.py --case case-001        # single case
    python evals/run_eval.py --verbose              # print full diagnosis
    python evals/run_eval.py --threshold 0.8        # CI exit: fail if < 80%

HOW IT WORKS
────────────
1. Load cases.jsonl — each case has fixture data and expected_keywords.
2. For each case, monkey-patch the kubectl/prom tool functions to return
   the fixture strings instead of calling the real binaries.
3. Invoke the full LangGraph (observe → hypothesize → propose).
4. Check that every expected_keyword appears (case-insensitive) in the
   final_diagnosis. If all match → PASS.
5. Print a summary table and exit with code 0 (all pass) or 1 (any fail).

COST ESTIMATE
─────────────
Each case makes ~3 LLM calls (observe + hypothesize + propose).
With model routing ON (haiku observe, sonnet reason):
  ~$0.002 per case × 5 cases ≈ $0.01 total

With routing OFF (all sonnet):
  ~$0.015 per case × 5 cases ≈ $0.08 total
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
import unittest.mock as mock
from pathlib import Path

# Add parent dir to path so we can import from src/
sys.path.insert(0, str(Path(__file__).parent.parent))

from dotenv import load_dotenv
load_dotenv(Path(__file__).parent.parent / ".env")

CASES_PATH = Path(__file__).parent / "cases.jsonl"
DEFAULT_THRESHOLD = 0.80


def load_cases(case_id: str | None = None) -> list[dict]:
    cases = []
    with open(CASES_PATH) as f:
        for line in f:
            line = line.strip()
            if line:
                cases.append(json.loads(line))
    if case_id:
        cases = [c for c in cases if c["id"] == case_id]
        if not cases:
            print(f"[error] case '{case_id}' not found in {CASES_PATH}", file=sys.stderr)
            sys.exit(1)
    return cases


def run_case(case: dict, verbose: bool = False) -> dict:
    """
    Run a single eval case with fixture data patched into the tool functions.

    Returns a result dict with: id, passed, missing_keywords, latency_ms, diagnosis.
    """
    fixtures = case["fixtures"]

    # ── Patch tool functions to return fixture data ──────────────────────────
    # We patch at the nodes module level so the already-compiled graph picks
    # up the patched functions. The patches must be active during graph.invoke().
    patches = [
        mock.patch(
            "src.graph.nodes.kubectl_get_pods",
            return_value=fixtures["pods"],
        ),
        mock.patch(
            "src.graph.nodes.kubectl_describe",
            return_value=fixtures["describe"],
        ),
        mock.patch(
            "src.graph.nodes.kubectl_logs",
            side_effect=lambda res, ns, **kw: (
                fixtures["prev_logs"] if kw.get("previous") else fixtures["logs"]
            ),
        ),
        mock.patch(
            "src.graph.nodes.kubectl_events",
            return_value=fixtures["events"],
        ),
        mock.patch(
            "src.graph.nodes.prom_query",
            return_value=fixtures["prom_up"],
        ),
    ]

    # Import after dotenv is loaded
    from src.graph.graph import k8s_doctor_graph
    from src.graph.state import initial_state

    state = initial_state(
        symptom=case["symptom"],
        namespace=case["namespace"],
        resource=case["resource"],
    )

    start = time.time()
    with (
        patches[0],
        patches[1],
        patches[2],
        patches[3],
        patches[4],
    ):
        try:
            result = k8s_doctor_graph.invoke(state)
        except Exception as exc:
            return {
                "id": case["id"],
                "passed": False,
                "missing_keywords": case["expected_keywords"],
                "latency_ms": int((time.time() - start) * 1000),
                "diagnosis": f"[ERROR] Graph execution failed: {exc}",
                "error": str(exc),
            }

    latency_ms = int((time.time() - start) * 1000)
    diagnosis = result.get("final_diagnosis", "")

    # ── Keyword check (case-insensitive) ─────────────────────────────────────
    diagnosis_lower = diagnosis.lower()
    missing = [
        kw for kw in case["expected_keywords"]
        if kw.lower() not in diagnosis_lower
    ]
    passed = len(missing) == 0

    if verbose:
        print(f"\n  {'─' * 50}")
        print(f"  Diagnosis for {case['id']}:")
        print(f"  {'─' * 50}")
        print(diagnosis)
        print()

    return {
        "id": case["id"],
        "passed": passed,
        "missing_keywords": missing,
        "latency_ms": latency_ms,
        "diagnosis": diagnosis,
    }


def print_summary(results: list[dict], threshold: float) -> bool:
    passed = sum(1 for r in results if r["passed"])
    total = len(results)
    rate = passed / total if total else 0.0

    print(f"\n{'=' * 60}")
    print(f"  K8s Doctor Eval — {passed}/{total} passed  ({rate * 100:.0f}%)")
    print(f"{'=' * 60}")

    for r in results:
        icon = "✅" if r["passed"] else "❌"
        latency = f"{r['latency_ms'] / 1000:.1f}s"
        missing_str = ""
        if not r["passed"]:
            missing_str = f"  missing: {r['missing_keywords']}"
        print(f"  {icon} {r['id']:<15} {latency:>6}{missing_str}")

    print(f"{'=' * 60}")
    threshold_pass = rate >= threshold
    threshold_icon = "✅" if threshold_pass else "❌"
    print(
        f"  {threshold_icon} Threshold {threshold * 100:.0f}%: "
        f"{'PASS' if threshold_pass else 'FAIL'}"
    )
    print(f"{'=' * 60}\n")
    return threshold_pass


def main() -> None:
    p = argparse.ArgumentParser(
        description="K8s Doctor offline eval runner",
    )
    p.add_argument("--case", default=None, help="Run a single case by ID")
    p.add_argument(
        "--verbose", "-v",
        action="store_true",
        help="Print full diagnosis for each case",
    )
    p.add_argument(
        "--threshold",
        type=float,
        default=DEFAULT_THRESHOLD,
        help=f"Minimum pass rate to exit 0 (default: {DEFAULT_THRESHOLD})",
    )
    args = p.parse_args()

    observe_model = os.environ.get("OBSERVE_MODEL", "claude-haiku-4-5-20251001")
    reason_model = os.environ.get("REASON_MODEL", "claude-sonnet-4-6")
    print(f"\nK8s Doctor Eval")
    print(f"  Observe model : {observe_model}")
    print(f"  Reason model  : {reason_model}")
    print(f"  Cases         : {CASES_PATH}")
    print()

    cases = load_cases(args.case)
    results = []

    for i, case in enumerate(cases, 1):
        print(f"  [{i}/{len(cases)}] {case['id']} — {case['description'][:55]}...", end="", flush=True)
        result = run_case(case, verbose=args.verbose)
        icon = "✅" if result["passed"] else "❌"
        print(f"  {icon}  ({result['latency_ms'] / 1000:.1f}s)")
        results.append(result)

    ok = print_summary(results, args.threshold)
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
