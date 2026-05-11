"""
metrics.py — Prometheus observability layer for the PR Reviewer agent.

WHAT THIS MODULE PROVIDES
──────────────────────────
Five metrics covering the cost, reliability, and security-finding picture:

  pr_reviewer_requests_total          Counter    Reviews processed, by status
  pr_reviewer_duration_seconds        Histogram  End-to-end run() latency
  pr_reviewer_tokens_total            Counter    LLM tokens consumed, by direction
  pr_reviewer_iterations_total        Histogram  ReAct loop iterations per review
  pr_reviewer_findings_total          Counter    Security findings, by severity

All registered on the default Prometheus registry.

GRACEFUL DEGRADATION
──────────────────────
Importable without prometheus_client installed — every symbol becomes a no-op.

METRICS ENDPOINT
────────────────
Call start_metrics_server() once at agent startup to expose /metrics on
http://localhost:METRICS_PORT (default 8001 for pr-reviewer to avoid clashing
with the slack-incident-bot on 8000).

  curl http://localhost:8001/metrics | grep pr_reviewer

REQUIRED ENV VARS
─────────────────
  METRICS_ENABLED=true
  METRICS_PORT=8001

PROMETHEUS QUERIES
──────────────────
  # Review throughput
  rate(pr_reviewer_requests_total{status="success"}[5m])

  # p95 review latency
  histogram_quantile(0.95, rate(pr_reviewer_duration_seconds_bucket[5m]))

  # Token burn rate
  rate(pr_reviewer_tokens_total{direction="prompt"}[5m])

  # HIGH/MEDIUM findings rate (security SLO signal)
  rate(pr_reviewer_findings_total{severity="HIGH"}[1h])
"""

from __future__ import annotations

import logging
import os
from typing import Any

logger = logging.getLogger(__name__)

# ── Optional prometheus_client import ─────────────────────────────────────────

try:
    from prometheus_client import Counter, Histogram, start_http_server

    _PROM_AVAILABLE = True
except ImportError:  # pragma: no cover
    _PROM_AVAILABLE = False
    logger.debug("prometheus_client not installed — metrics are disabled")


# ── Metric definitions ────────────────────────────────────────────────────────


def _make_metrics() -> dict[str, Any]:
    """Create and return all metrics, or empty stubs when prom unavailable.

    Handles duplicate registration (e.g. module reload in tests) by catching
    ValueError and returning an empty dict — record_*() helpers become no-ops.
    """
    if not _PROM_AVAILABLE:
        return {}

    try:
        return {
            "requests": Counter(
                "pr_reviewer_requests_total",
                "Total PR reviews processed by the PR reviewer agent",
                ["status"],  # "success" | "error"
            ),
            "duration": Histogram(
                "pr_reviewer_duration_seconds",
                "End-to-end latency of PRReviewerPlanner.run()",
                buckets=[5.0, 10.0, 20.0, 30.0, 60.0, 120.0, 180.0, 300.0],
            ),
            "tokens": Counter(
                "pr_reviewer_tokens_total",
                "LLM tokens consumed by the PR reviewer agent",
                ["direction"],  # "prompt" | "completion"
            ),
            "iterations": Histogram(
                "pr_reviewer_iterations_total",
                "Number of ReAct loop iterations per PR review",
                buckets=[1, 2, 3, 5, 8, 10, 15, 20],
            ),
            "findings": Counter(
                "pr_reviewer_findings_total",
                "Security findings identified by the PR reviewer, by severity",
                ["severity"],  # "HIGH" | "MEDIUM" | "LOW" | "INFO"
            ),
        }
    except ValueError:
        logger.debug("Prometheus metrics already registered — skipping re-registration")
        return {}


_METRICS: dict[str, Any] = _make_metrics()


# ── Public helpers ────────────────────────────────────────────────────────────


def metrics_enabled() -> bool:
    """Return True when prometheus_client is installed and METRICS_ENABLED != false."""
    if not _PROM_AVAILABLE:
        return False
    return os.environ.get("METRICS_ENABLED", "true").lower() != "false"


def start_metrics_server(port: int | None = None) -> None:
    """Start the background Prometheus HTTP server on /metrics.

    Default port is 8001 (pr-reviewer) to avoid clashing with the
    slack-incident-bot which defaults to 8000.

    Args:
        port: TCP port. Defaults to METRICS_PORT env var, falling back to 8001.
    """
    if not metrics_enabled():
        logger.info("Prometheus metrics disabled (METRICS_ENABLED=false or package missing)")
        return

    resolved_port = port or int(os.environ.get("METRICS_PORT", "8001"))
    start_http_server(resolved_port)
    logger.info("PR reviewer metrics available at http://localhost:%d/metrics", resolved_port)


def record_request(status: str) -> None:
    """Increment the request counter.

    Args:
        status: "success" or "error"
    """
    if not metrics_enabled():
        return
    _METRICS["requests"].labels(status=status).inc()


def record_duration(seconds: float) -> None:
    """Record end-to-end review latency.

    Args:
        seconds: Elapsed wall-clock time in seconds.
    """
    if not metrics_enabled():
        return
    _METRICS["duration"].observe(seconds)


def record_tokens(prompt_tokens: int, completion_tokens: int) -> None:
    """Record LLM token counts from a single LLM response.

    Args:
        prompt_tokens:     Input token count.
        completion_tokens: Output token count.
    """
    if not metrics_enabled():
        return
    _METRICS["tokens"].labels(direction="prompt").inc(prompt_tokens)
    _METRICS["tokens"].labels(direction="completion").inc(completion_tokens)


def record_iterations(count: int) -> None:
    """Record the number of ReAct loop iterations for a completed review.

    Args:
        count: Total iterations used.
    """
    if not metrics_enabled():
        return
    _METRICS["iterations"].observe(count)


def record_findings(findings: list[dict]) -> None:
    """Record security findings by severity from the completed review.

    Args:
        findings: List of finding dicts, each with a 'severity' key.
                  Severities not in HIGH/MEDIUM/LOW/INFO are counted as INFO.
    """
    if not metrics_enabled():
        return
    valid_severities = {"HIGH", "MEDIUM", "LOW", "INFO"}
    for finding in findings:
        sev = str(finding.get("severity", "INFO")).upper()
        if sev not in valid_severities:
            sev = "INFO"
        _METRICS["findings"].labels(severity=sev).inc()
