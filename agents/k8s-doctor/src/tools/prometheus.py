"""
src/tools/prometheus.py — Prometheus query tool for the K8s Doctor agent.

Queries Prometheus via its HTTP API (direct) or via the MCP server
(services/mcp-prometheus/) when MCP_PROMETHEUS_URL is set.

TOOLS
─────
  prom_query(query, prometheus_url)  → instant query result as a string
  prom_query_range(query, ...)       → range query (for trend detection)

USAGE IN GRAPH
──────────────
The observe node calls prom_query to check:
  - container_restarts_total    → how many times has the pod restarted?
  - kube_pod_container_status_waiting_reason → what is the wait reason?
  - up{job="kubernetes-pods"}   → is the pod target healthy?
"""

from __future__ import annotations

import logging
import os

import requests

log = logging.getLogger(__name__)

DEFAULT_PROMETHEUS_URL = os.environ.get(
    "PROMETHEUS_URL", "http://localhost:9090"
)
DEFAULT_TIMEOUT = 10  # seconds


def prom_query(
    query: str,
    prometheus_url: str = DEFAULT_PROMETHEUS_URL,
) -> str:
    """
    Run an instant PromQL query against Prometheus and return the result.

    Returns a human-readable string of the metric name + value pairs,
    or an error message if Prometheus is unreachable or the query fails.

    Args:
        query:           PromQL expression (e.g. "up", "container_restart_count")
        prometheus_url:  Base URL of Prometheus (default: http://localhost:9090)

    Examples:
        prom_query("up")
        prom_query('kube_pod_status_phase{namespace="doctor-lab"}')
        prom_query('rate(container_cpu_usage_seconds_total[5m])')
    """
    url = f"{prometheus_url}/api/v1/query"
    try:
        resp = requests.get(
            url,
            params={"query": query},
            timeout=DEFAULT_TIMEOUT,
        )
        resp.raise_for_status()
        data = resp.json()

        if data.get("status") != "success":
            return f"[Prometheus error] {data.get('error', 'unknown error')}"

        results = data.get("data", {}).get("result", [])
        if not results:
            return f"[No data] Query returned no results: {query}"

        lines = [f"PromQL: {query}"]
        for item in results:
            metric = item.get("metric", {})
            value = item.get("value", [None, "?"])[1]
            label_str = ", ".join(f'{k}="{v}"' for k, v in metric.items())
            lines.append(f"  {{{label_str}}} = {value}")
        return "\n".join(lines)

    except requests.exceptions.ConnectionError:
        return (
            f"[ERROR] Cannot connect to Prometheus at {prometheus_url}. "
            "Is the observability stack running? (make obs-up)"
        )
    except requests.exceptions.Timeout:
        return f"[ERROR] Prometheus query timed out after {DEFAULT_TIMEOUT}s"
    except Exception as exc:
        return f"[ERROR] prom_query failed: {exc}"


def prom_query_range(
    query: str,
    start: str,
    end: str,
    step: str = "1m",
    prometheus_url: str = DEFAULT_PROMETHEUS_URL,
) -> str:
    """
    Run a range PromQL query and return a summary of min/max/latest values.

    Useful for trend detection — e.g. is restart count growing, or stable?

    Args:
        query:           PromQL expression
        start:           Start time in RFC3339 or Unix timestamp (e.g. "now-1h")
        end:             End time (e.g. "now")
        step:            Resolution step (default: "1m")
        prometheus_url:  Base URL of Prometheus
    """
    url = f"{prometheus_url}/api/v1/query_range"
    try:
        resp = requests.get(
            url,
            params={"query": query, "start": start, "end": end, "step": step},
            timeout=DEFAULT_TIMEOUT,
        )
        resp.raise_for_status()
        data = resp.json()

        if data.get("status") != "success":
            return f"[Prometheus error] {data.get('error', 'unknown error')}"

        results = data.get("data", {}).get("result", [])
        if not results:
            return f"[No data] Range query returned no results: {query}"

        lines = [f"PromQL range: {query} ({start} → {end}, step={step})"]
        for item in results:
            metric = item.get("metric", {})
            values = [float(v[1]) for v in item.get("values", [])]
            if values:
                label_str = ", ".join(f'{k}="{v}"' for k, v in metric.items())
                lines.append(
                    f"  {{{label_str}}}: min={min(values):.2f} "
                    f"max={max(values):.2f} latest={values[-1]:.2f}"
                )
        return "\n".join(lines)

    except Exception as exc:
        return f"[ERROR] prom_query_range failed: {exc}"
