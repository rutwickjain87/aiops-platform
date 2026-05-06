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
    def __init__(self, agent_factory, cases_path: str = "evals/cases.jsonl"):
        self.agent_factory = agent_factory  # callable returning a fresh agent per case
        self.cases = [json.loads(l) for l in Path(cases_path).read_text().splitlines() if l.strip()]

    def run(self) -> list[CaseResult]:
        results = []
        for case in self.cases:
            agent = self.agent_factory()
            try:
                output = agent.run(case["input"])
                passed, notes = self._grade(case, output)
            except Exception as e:
                passed, notes = False, f"agent error: {e}"
            results.append(CaseResult(case["id"], passed, notes, latency_ms=0, cost_usd=0.0))
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
            print(f"  [{mark}] {r.case_id}{' — ' + r.notes if r.notes else ''}")
