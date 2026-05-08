"""
Unit tests for evaluator.py — pure Python, no API keys required.

Tests cover:
  - CaseResult dataclass construction and fields
  - Evaluator._grade() for all three rubric types (contains / exact / llm-judge)
  - Evaluator._report() latency summary computation
  - Edge cases: empty output, unknown rubric, case-insensitive miss
"""
from __future__ import annotations

import sys
from pathlib import Path

# Make the log-intelligence agent importable without installing it
sys.path.insert(0, str(Path(__file__).parent.parent / "agents" / "log-intelligence"))

from evaluator import CaseResult, Evaluator  # noqa: E402


# ── CaseResult ─────────────────────────────────────────────────────────────────

class TestCaseResult:
    def test_fields_stored(self):
        r = CaseResult(
            case_id="case-001",
            passed=True,
            notes="",
            latency_ms=1234,
            cost_usd=0.0012,
        )
        assert r.case_id == "case-001"
        assert r.passed is True
        assert r.notes == ""
        assert r.latency_ms == 1234
        assert r.cost_usd == 0.0012

    def test_failed_case(self):
        r = CaseResult(
            case_id="case-002",
            passed=False,
            notes="missing: 'P2'",
            latency_ms=500,
            cost_usd=0.0,
        )
        assert r.passed is False
        assert "P2" in r.notes


# ── Evaluator._grade() ─────────────────────────────────────────────────────────

class TestGrade:
    """Test _grade() directly by instantiating an Evaluator with a stub factory."""

    def _make_evaluator(self, tmp_path):
        """Return an Evaluator wired to a dummy cases file."""
        cases_file = tmp_path / "cases.jsonl"
        cases_file.write_text('{"id":"c1","input":"x","expected":"P2","rubric":"contains"}\n')
        # Agent factory is never called in these tests — we call _grade() directly
        return Evaluator(agent_factory=lambda: None, cases_path=str(cases_file),
                         sleep_between_cases=0)

    def test_contains_pass(self, tmp_path):
        ev = self._make_evaluator(tmp_path)
        ok, notes = ev._grade({"expected": "P2", "rubric": "contains"}, "## Severity\nP2 — …")
        assert ok is True

    def test_contains_fail(self, tmp_path):
        ev = self._make_evaluator(tmp_path)
        ok, notes = ev._grade({"expected": "P2", "rubric": "contains"}, "## Severity\nP3 — …")
        assert ok is False
        assert "P2" in notes

    def test_contains_empty_output(self, tmp_path):
        ev = self._make_evaluator(tmp_path)
        ok, notes = ev._grade({"expected": "DataXceiver", "rubric": "contains"}, "")
        assert ok is False

    def test_exact_pass(self, tmp_path):
        ev = self._make_evaluator(tmp_path)
        ok, _ = ev._grade({"expected": "P1", "rubric": "exact"}, "P1")
        assert ok is True

    def test_exact_fail_whitespace(self, tmp_path):
        ev = self._make_evaluator(tmp_path)
        # strip() is applied, so leading/trailing space is fine
        ok, _ = ev._grade({"expected": "P1", "rubric": "exact"}, "  P1  ")
        assert ok is True

    def test_exact_fail_mismatch(self, tmp_path):
        ev = self._make_evaluator(tmp_path)
        ok, notes = ev._grade({"expected": "P1", "rubric": "exact"}, "P2")
        assert ok is False
        assert "P1" in notes

    def test_llm_judge_stub_always_passes(self, tmp_path):
        ev = self._make_evaluator(tmp_path)
        ok, notes = ev._grade({"expected": "", "rubric": "llm-judge"}, "anything")
        assert ok is True
        assert "stub" in notes

    def test_unknown_rubric_fails(self, tmp_path):
        ev = self._make_evaluator(tmp_path)
        ok, notes = ev._grade({"expected": "x", "rubric": "regex"}, "x")
        assert ok is False
        assert "unknown rubric" in notes

    def test_default_rubric_is_contains(self, tmp_path):
        """When rubric key is absent, it should default to 'contains'."""
        ev = self._make_evaluator(tmp_path)
        ok, _ = ev._grade({"expected": "DataNode"}, "Error in DataNode thread")
        assert ok is True


# ── Evaluator._report() latency stats ─────────────────────────────────────────

class TestReport:
    def test_report_no_crash_on_empty(self, capsys):
        """_report() must not crash on an empty result list."""
        # Build a minimal Evaluator without a real cases file
        import tempfile, json
        with tempfile.NamedTemporaryFile(mode="w", suffix=".jsonl", delete=False) as f:
            f.write(json.dumps({"id": "c1", "input": "x", "expected": "y",
                                "rubric": "contains"}) + "\n")
            path = f.name
        ev = Evaluator(agent_factory=lambda: None, cases_path=path, sleep_between_cases=0)
        ev._report([])   # should not raise
        out = capsys.readouterr().out
        assert "0/0" in out

    def test_report_prints_latency_summary(self, capsys):
        import tempfile, json
        with tempfile.NamedTemporaryFile(mode="w", suffix=".jsonl", delete=False) as f:
            f.write(json.dumps({"id": "c1", "input": "x", "expected": "y",
                                "rubric": "contains"}) + "\n")
            path = f.name
        ev = Evaluator(agent_factory=lambda: None, cases_path=path, sleep_between_cases=0)
        results = [
            CaseResult("c1", True, "", latency_ms=100, cost_usd=0.0),
            CaseResult("c2", True, "", latency_ms=200, cost_usd=0.0),
            CaseResult("c3", False, "missing x", latency_ms=300, cost_usd=0.0),
        ]
        ev._report(results)
        out = capsys.readouterr().out
        assert "p50" in out
        assert "p95" in out
        assert "2/3" in out
