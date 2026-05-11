"""
metrics.py — Prometheus observability layer for the Slack Incident Bot.

WHAT THIS MODULE PROVIDES
──────────────────────────
Four metrics that cover the full cost and reliability picture of the agent:

  incident_bot_requests_total          Counter    Alerts processed, by status
  incident_bot_duration_seconds        Histogram  End-to-end handle_alert latency
  incident_bot_tokens_total            Counter    LLM tokens consumed, by direction
  incident_bot_iterations_total        Histogram  ReAct loop iterations per alert

All are registered on the default Prometheus registry.

GRACEFUL DEGRADATION
──────────────────────
If prometheus_client is not installed the module is still importable — every
symbol becomes a no-op so the bot runs identically without metrics.

METRICS ENDPOINT
────────────────
Call start_metrics_server() once at bot startup.  It launches a background
HTTP server (default port 8000) that exposes /metrics in the Prometheus
text exposition format.

  curl http://localhost:8000/metrics

REQUIRED ENV VARS (add to .env)
────────────────────────────────
  METRICS_ENABLED=true     Set to "false" to skip starting the HTTP server
  METRICS_PORT=8000        Port for the /metrics endpoint (default 8000)

WHAT YOU SEE IN PROMETHEUS / GRAFANA
──────────────────────────────────────
  # Alert throughput
  rate(incident_bot_requests_total{status="success"}[5m])

  # p95 end-to-end latency
  histogram_quantile(0.95, rate(incident_bot_duration_seconds_bucket[5m]))

  # Token burn rate (cost proxy)
  rate(incident_bot_tokens_total{direction="prompt"}[5m])
  rate(incident_bot_tokens_total{direction="completion"}[5m])

  # Average ReAct iterations (LLM reasoning efficiency)
  rate(incident_bot_iterations_total_sum[5m])
  / rate(incident_bot_iterations_total_count[5m])
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

    Handles duplicate registration gracefully — prometheus_client raises
    ValueError if the same metric name is registered twice (e.g. on module
    reload in tests).  We catch that and return an empty dict, which causes
    all record_*() helpers to become no-ops for that process lifetime.
    """
    if not _PROM_AVAILABLE:
        return {}

    try:
        return {
            "requests": Counter(
                "incident_bot_requests_total",
                "Total alerts processed by the incident bot",
                ["status"],  # "success" | "error"
            ),
            "duration": Histogram(
                "incident_bot_duration_seconds",
                "End-to-end latency of handle_alert()",
                buckets=[0.5, 1.0, 2.0, 5.0, 10.0, 20.0, 30.0, 60.0],
            ),
            "tokens": Counter(
                "incident_bot_tokens_total",
                "LLM tokens consumed by the incident bot",
                ["direction"],  # "prompt" | "completion"
            ),
            "iterations": Histogram(
                "incident_bot_iterations_total",
                "Number of ReAct loop iterations per alert",
                buckets=[1, 2, 3, 4, 5, 6, 7, 8, 9, 10],
            ),
        }
    except ValueError:
        # Already registered — module was reloaded (common in tests).
        # Return empty dict so record_* helpers silently become no-ops.
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

    Safe to call multiple times — the server is only started when
    metrics_enabled() returns True.

    Args:
        port: TCP port to listen on.  Defaults to the METRICS_PORT env var,
              falling back to 8000.
    """
    if not metrics_enabled():
        logger.info("Prometheus metrics disabled (METRICS_ENABLED=false or package missing)")
        return

    resolved_port = port or int(os.environ.get("METRICS_PORT", "8000"))
    start_http_server(resolved_port)
    logger.info("Prometheus metrics available at http://localhost:%d/metrics", resolved_port)


def record_request(status: str) -> None:
    """Increment the request counter.

    Args:
        status: "success" or "error"
    """
    if not metrics_enabled():
        return
    _METRICS["requests"].labels(status=status).inc()


def record_duration(seconds: float) -> None:
    """Record handle_alert end-to-end latency.

    Args:
        seconds: Elapsed wall-clock time in seconds.
    """
    if not metrics_enabled():
        return
    _METRICS["duration"].observe(seconds)


def record_tokens(prompt_tokens: int, completion_tokens: int) -> None:
    """Record LLM token counts from a single messages.create() response.

    Args:
        prompt_tokens:     Input token count from response.usage.input_tokens.
        completion_tokens: Output token count from response.usage.output_tokens.
    """
    if not metrics_enabled():
        return
    _METRICS["tokens"].labels(direction="prompt").inc(prompt_tokens)
    _METRICS["tokens"].labels(direction="completion").inc(completion_tokens)


def record_iterations(count: int) -> None:
    """Record the number of ReAct loop iterations for a completed alert.

    Args:
        count: Total iterations used (each iteration = one LLM call).
    """
    if not metrics_enabled():
        return
    _METRICS["iterations"].observe(count)
