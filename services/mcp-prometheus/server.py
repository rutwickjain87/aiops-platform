"""
services/mcp-prometheus/server.py — Prometheus MCP server.

Exposes Prometheus as an MCP tool so any MCP-compatible agent (Claude Desktop,
LangGraph, etc.) can query metrics without knowing the HTTP API.

TOOLS EXPOSED
─────────────
  prom_query(query)             → instant PromQL query result
  prom_query_range(query, ...)  → range query with min/max/latest summary
  prom_targets()                → list all active scrape targets + health

RUNNING
───────
  # stdio transport (default) — used by MCP clients
  python server.py

  # Test it directly from the mcp CLI:
  echo '{"jsonrpc":"2.0","id":1,"method":"tools/call","params":{"name":"prom_query","arguments":{"query":"up"}}}' \
    | python server.py

WIRING INTO K8S DOCTOR
───────────────────────
  Set MCP_PROMETHEUS_SERVER=true in agents/k8s-doctor/.env to have
  prom_query() in tools/prometheus.py route through this server instead
  of calling Prometheus HTTP directly.

WHY AN MCP SERVER?
──────────────────
MCP (Model Context Protocol) decouples tool execution from the agent.
The agent sends a JSON-RPC call; the server handles auth, retries, and
result formatting. Swapping from local Prometheus to a remote one only
requires changing the server's PROMETHEUS_URL — zero agent code changes.
"""

from __future__ import annotations

import logging
import os

import requests
from mcp.server.fastmcp import FastMCP

log = logging.getLogger(__name__)

PROMETHEUS_URL = os.environ.get("PROMETHEUS_URL", "http://localhost:9090")
DEFAULT_TIMEOUT = 10

# ── Create the MCP server ─────────────────────────────────────────────────────
mcp = FastMCP(
    name="prometheus",
    instructions=(
        "Query Prometheus metrics using PromQL. "
        "Use prom_query for instant values, prom_query_range for trends, "
        "and prom_targets to see what is being scraped."
    ),
)


# ── Tool: prom_query ──────────────────────────────────────────────────────────

@mcp.tool()
def prom_query(query: str) -> str:
    """
    Run an instant PromQL query against Prometheus.

    Returns metric label sets with their current values, or an error message
    if Prometheus is unreachable or the query returns no data.

    Args:
        query: PromQL expression to evaluate.
               Examples:
                 "up"
                 'kube_pod_status_phase{namespace="doctor-lab"}'
                 'rate(container_cpu_usage_seconds_total[5m])'
    """
    url = f"{PROMETHEUS_URL}/api/v1/query"
    try:
        resp = requests.get(url, params={"query": query}, timeout=DEFAULT_TIMEOUT)
        resp.raise_for_status()
        data = resp.json()

        if data.get("status") != "success":
            return f"Prometheus error: {data.get('error', 'unknown')}"

        results = data.get("data", {}).get("result", [])
        if not results:
            return f"No data returned for query: {query}"

        lines = [f"Query: {query}"]
        for item in results:
            metric = item.get("metric", {})
            value = item.get("value", [None, "?"])[1]
            label_str = ", ".join(f'{k}="{v}"' for k, v in metric.items())
            lines.append(f"  {{{label_str}}} = {value}")
        return "\n".join(lines)

    except requests.exceptions.ConnectionError:
        return f"Cannot connect to Prometheus at {PROMETHEUS_URL}"
    except Exception as exc:
        return f"prom_query failed: {exc}"


# ── Tool: prom_query_range ────────────────────────────────────────────────────

@mcp.tool()
def prom_query_range(
    query: str,
    start: str = "now-1h",
    end: str = "now",
    step: str = "1m",
) -> str:
    """
    Run a range PromQL query and return min/max/latest for each time series.

    Useful for detecting trends: is container restart count growing?
    Is CPU spiking? Is memory growing toward the limit?

    Args:
        query: PromQL expression to evaluate over time.
        start: Start time — RFC3339, Unix timestamp, or relative (e.g. "now-1h").
        end:   End time — same formats as start (default: "now").
        step:  Resolution step (default: "1m"). Coarser = faster query.
    """
    url = f"{PROMETHEUS_URL}/api/v1/query_range"
    try:
        resp = requests.get(
            url,
            params={"query": query, "start": start, "end": end, "step": step},
            timeout=DEFAULT_TIMEOUT,
        )
        resp.raise_for_status()
        data = resp.json()

        if data.get("status") != "success":
            return f"Prometheus error: {data.get('error', 'unknown')}"

        results = data.get("data", {}).get("result", [])
        if not results:
            return f"No data for range query: {query} ({start}→{end})"

        lines = [f"Range query: {query} ({start}→{end}, step={step})"]
        for item in results:
            metric = item.get("metric", {})
            values = [float(v[1]) for v in item.get("values", []) if v[1] != "NaN"]
            if values:
                label_str = ", ".join(f'{k}="{v}"' for k, v in metric.items())
                lines.append(
                    f"  {{{label_str}}}: "
                    f"min={min(values):.3f} max={max(values):.3f} latest={values[-1]:.3f}"
                )
        return "\n".join(lines)

    except Exception as exc:
        return f"prom_query_range failed: {exc}"


# ── Tool: prom_targets ────────────────────────────────────────────────────────

@mcp.tool()
def prom_targets() -> str:
    """
    List all active Prometheus scrape targets and their health status.

    Returns each target's job name, instance, health (up/down), and last
    scrape time. Use this to verify that agent metrics endpoints are reachable.
    """
    url = f"{PROMETHEUS_URL}/api/v1/targets"
    try:
        resp = requests.get(url, timeout=DEFAULT_TIMEOUT)
        resp.raise_for_status()
        data = resp.json()

        active = data.get("data", {}).get("activeTargets", [])
        if not active:
            return "No active scrape targets found."

        lines = [f"Active targets ({len(active)} total):"]
        for t in active:
            job = t.get("labels", {}).get("job", "?")
            instance = t.get("labels", {}).get("instance", "?")
            health = t.get("health", "?")
            last_scrape = t.get("lastScrape", "?")
            error = t.get("lastError", "")
            status = f"{'✅' if health == 'up' else '❌'} {health}"
            line = f"  [{status}] {job} — {instance}  (last: {last_scrape})"
            if error:
                line += f"\n          ERROR: {error}"
            lines.append(line)
        return "\n".join(lines)

    except Exception as exc:
        return f"prom_targets failed: {exc}"


# ── Entry point ───────────────────────────────────────────────────────────────

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    log.info("Starting Prometheus MCP server (Prometheus: %s)", PROMETHEUS_URL)
    mcp.run(transport="stdio")
