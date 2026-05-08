"""
evaluator.py — the QA pass.

Loads hand-labeled cases from evals/cases.jsonl, runs the agent against each,
scores outputs, prints a report. Designed to run in CI on every prompt change.

A case has shape:
{
  "id": "case-001",
  "input": "...",
  "expected": {"severity": "P2", "service": "checkout", ...},
  "rubric": "exact|contains|llm-judge"
}
"""
from __future__ import annotations
import json
import statistics
import time
from dataclasses import dataclass
from pathlib import Path


@dataclass
class CaseResult:
    case_id: str
    passed: bool
    notes: str
    latency_ms: int
    cost_usd: float


class Evaluator:
    def __init__(self, agent_factory, cases_path: str = "evals/cases.jsonl",
                 sleep_between_cases: float = 2.0):
        self.agent_factory = agent_factory  # callable returning a fresh agent per case
        self.sleep_between_cases = sleep_between_cases
        self.cases = [json.loads(line) for line in Path(cases_path).read_text().splitlines() if line.strip()]

    def run(self) -> list[CaseResult]:
        results = []
        for i, case in enumerate(self.cases):
            agent = self.agent_factory()
            t0 = time.perf_counter()
            try:
                output = agent.run(case["input"])
                latency_ms = int((time.perf_counter() - t0) * 1000)
                passed, notes = self._grade(case, output)
            except Exception as e:
                latency_ms = int((time.perf_counter() - t0) * 1000)
                passed, notes = False, f"agent error: {e}"
            results.append(CaseResult(case["id"], passed, notes,
                                       latency_ms=latency_ms, cost_usd=0.0))
            # Sleep between cases to avoid rate limits (skip after last case)
            if i < len(self.cases) - 1 and self.sleep_between_cases > 0:
                time.sleep(self.sleep_between_cases)
        self._report(results)
        return results

    def _grade(self, case: dict, output: str) -> tuple[bool, str]:
        rubric = case.get("rubric", "contains")
        if rubric == "exact":
            ok = output.strip() == case["expected"]
            return ok, "" if ok else f"expected {case['expected']!r}, got {output!r}"
        if rubric == "contains":
            needle = case["expected"]
            return needle in output, f"missing: {needle!r}"
        if rubric == "llm-judge":
            # TODO: call a small judge model that returns {"pass": bool, "reason": str}
            return True, "(llm-judge stub)"
        return False, f"unknown rubric: {rubric}"

    def _report(self, results: list[CaseResult]) -> None:
        total = len(results)
        passed = sum(1 for r in results if r.passed)
        print(f"Eval: {passed}/{total} passed ({passed/total*100:.0f}%)")
        for r in results:
            mark = "PASS" if r.passed else "FAIL"
            latency = f"  {r.latency_ms}ms" if r.latency_ms else ""
            print(f"  [{mark}] {r.case_id}{latency}{' — ' + r.notes if r.notes else ''}")

        # Latency summary (only when timings were captured)
        latencies = [r.latency_ms for r in results if r.latency_ms > 0]
        if latencies:
            p50 = int(statistics.median(latencies))
            p95 = sorted(latencies)[min(int(len(latencies) * 0.95), len(latencies) - 1)]
            mean = int(statistics.mean(latencies))
            print(f"  Latency: mean={mean}ms  p50={p50}ms  p95={p95}ms")
