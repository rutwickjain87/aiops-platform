"""
Unit tests for run_experiment.py — pure Python, no API keys required.

Tests cover:
  - grade() function for contains and exact rubrics
  - ModelRow computed properties (pass_rate, p50, p95, avg_cost)
  - _model_slug() helper
  - CaseResult.cost_usd() calculation
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "agents" / "log-intelligence"))

from run_experiment import CaseResult, ModelRow, _model_slug, grade  # noqa: E402, I001


# ── grade() ───────────────────────────────────────────────────────────────────


class TestGrade:
    def test_contains_hit(self):
        ok, notes = grade(
            {"expected": "P2", "rubric": "contains"}, "Severity: P2 outage"
        )
        assert ok is True
        assert notes == ""

    def test_contains_miss(self):
        ok, notes = grade({"expected": "P1"}, "Severity: P3")
        assert ok is False
        assert "P1" in notes

    def test_exact_pass(self):
        ok, _ = grade({"expected": "P1", "rubric": "exact"}, "P1")
        assert ok is True

    def test_exact_fail(self):
        ok, notes = grade({"expected": "P1", "rubric": "exact"}, "P2")
        assert ok is False

    def test_llm_judge_stub(self):
        ok, notes = grade({"expected": "", "rubric": "llm-judge"}, "anything")
        assert ok is True
        assert "stub" in notes


# ── CaseResult.cost_usd() ─────────────────────────────────────────────────────


class TestCaseResultCost:
    def test_cost_calculation(self):
        r = CaseResult(
            case_id="c1",
            passed=True,
            notes="",
            latency_ms=5000,
            input_tokens=100_000,
            output_tokens=2_000,
        )
        # Sonnet pricing: $3/1M input, $15/1M output
        cost = r.cost_usd(in_usd_1m=3.00, out_usd_1m=15.00)
        assert (
            abs(cost - (100_000 / 1_000_000 * 3.00 + 2_000 / 1_000_000 * 15.00)) < 1e-9
        )

    def test_zero_tokens_zero_cost(self):
        r = CaseResult(
            case_id="c1",
            passed=False,
            notes="error",
            latency_ms=100,
            input_tokens=0,
            output_tokens=0,
        )
        assert r.cost_usd(3.00, 15.00) == 0.0


# ── ModelRow computed properties ──────────────────────────────────────────────


class TestModelRow:
    def _make_row(self):
        results = [
            CaseResult("c1", True, "", 10000, 80000, 1500),
            CaseResult("c2", True, "", 20000, 90000, 1800),
            CaseResult("c3", False, "miss", 15000, 70000, 1200),
            CaseResult("c4", True, "", 12000, 85000, 1600),
            CaseResult("c5", True, "", 18000, 95000, 2000),
        ]
        return ModelRow(
            model_id="anthropic/claude-haiku-4-5",
            label="Claude Haiku 4.5",
            results=results,
            in_usd_1m=0.25,
            out_usd_1m=1.25,
        )

    def test_pass_rate_string(self):
        row = self._make_row()
        assert row.pass_rate == "4/5 (80%)"

    def test_total(self):
        assert self._make_row().total == 5

    def test_p50_latency(self):
        row = self._make_row()
        # latencies: 10000, 12000, 15000, 18000, 20000 → median = 15000
        assert row.p50_ms == 15000.0

    def test_p95_latency(self):
        row = self._make_row()
        # p95 of 5 values → index min(4, 4) = 4 → 20000
        assert row.p95_ms == 20000.0

    def test_empty_row_pass_rate(self):
        row = ModelRow(model_id="x", label="x", in_usd_1m=1.0, out_usd_1m=1.0)
        assert row.pass_rate == "—"

    def test_total_tokens(self):
        row = self._make_row()
        assert row.total_input_tokens == 80000 + 90000 + 70000 + 85000 + 95000
        assert row.total_output_tokens == 1500 + 1800 + 1200 + 1600 + 2000


# ── _model_slug() ─────────────────────────────────────────────────────────────


class TestModelSlug:
    def test_slash_replaced(self):
        assert _model_slug("anthropic/claude-haiku-4-5") == "anthropic-claude-haiku-4-5"

    def test_openai_model(self):
        assert _model_slug("openai/gpt-4o-mini") == "openai-gpt-4o-mini"

    def test_no_slash(self):
        assert _model_slug("plain-model") == "plain-model"
