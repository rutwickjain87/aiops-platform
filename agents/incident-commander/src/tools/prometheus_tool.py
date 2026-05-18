"""
Prometheus query tool for the Incident Investigator agent.
Queries the Prometheus HTTP API for metrics around the incident window.
"""
import os
import logging
from crewai.tools import tool

import requests

log = logging.getLogger(__name__)
PROMETHEUS_URL = os.environ.get("PROMETHEUS_URL", "http://localhost:9090")


def _query(promql: str) -> dict:
    """Run an instant PromQL query, return parsed JSON or error dict."""
    try:
        resp = requests.get(
            f"{PROMETHEUS_URL}/api/v1/query",
            params={"query": promql},
            timeout=10,
        )
        resp.raise_for_status()
        return resp.json()
    except requests.exceptions.ConnectionError:
        return {"error": f"Cannot connect to Prometheus at {PROMETHEUS_URL}"}
    except Exception as exc:
        return {"error": str(exc)}


def _format_result(data: dict) -> str:
    if "error" in data:
        return f"ERROR: {data['error']}"
    results = data.get("data", {}).get("result", [])
    if not results:
        return "No data returned (series may not exist)"
    lines = []
    for r in results[:10]:  # cap output
        metric = r.get("metric", {})
        value = r.get("value", [None, "N/A"])[1]
        label_str = ", ".join(f"{k}={v}" for k, v in metric.items() if k != "__name__")
        lines.append(f"  {label_str}: {value}")
    return "\n".join(lines)


@tool("query_error_rate")
def query_error_rate(namespace_and_service: str) -> str:
    """
    Query the HTTP 5xx error rate for a service in a namespace.
    Input format: "<namespace>/<service>" — e.g. "payments/payments-api".
    Returns the error rate as a percentage.
    """
    parts = namespace_and_service.strip().split("/")
    if len(parts) != 2:
        return "ERROR: expected 'namespace/service'"
    ns, svc = parts
    promql = (
        f'sum(rate(http_requests_total{{namespace="{ns}",service="{svc}",code=~"5.."}}[5m])) / '
        f'sum(rate(http_requests_total{{namespace="{ns}",service="{svc}"}}[5m])) * 100'
    )
    return _format_result(_query(promql))


@tool("query_memory_usage")
def query_memory_usage(namespace_and_pod: str) -> str:
    """
    Query container memory usage for a pod or all pods in a namespace.
    Input format: "<namespace>/<pod-name>" or "<namespace>/all".
    """
    parts = namespace_and_pod.strip().split("/")
    if len(parts) != 2:
        return "ERROR: expected 'namespace/pod' or 'namespace/all'"
    ns, pod = parts
    if pod == "all":
        promql = f'container_memory_working_set_bytes{{namespace="{ns}",container!=""}}'
    else:
        promql = f'container_memory_working_set_bytes{{namespace="{ns}",pod=~"{pod}.*",container!=""}}'
    return _format_result(_query(promql))


@tool("query_cpu_usage")
def query_cpu_usage(namespace_and_pod: str) -> str:
    """
    Query CPU usage rate for a pod.
    Input format: "<namespace>/<pod-name>" or "<namespace>/all".
    """
    parts = namespace_and_pod.strip().split("/")
    if len(parts) != 2:
        return "ERROR: expected 'namespace/pod' or 'namespace/all'"
    ns, pod = parts
    if pod == "all":
        promql = f'sum(rate(container_cpu_usage_seconds_total{{namespace="{ns}",container!=""}}[5m])) by (pod)'
    else:
        promql = f'sum(rate(container_cpu_usage_seconds_total{{namespace="{ns}",pod=~"{pod}.*",container!=""}}[5m])) by (pod)'
    return _format_result(_query(promql))


@tool("query_pod_restarts")
def query_pod_restarts(namespace: str) -> str:
    """
    Query restart counts for all pods in a namespace over the last 30 minutes.
    Input: namespace name.
    """
    promql = f'increase(kube_pod_container_status_restarts_total{{namespace="{namespace.strip()}"}}[30m])'
    return _format_result(_query(promql))


@tool("query_node_disk_usage")
def query_node_disk_usage(node: str) -> str:
    """
    Query disk usage percentage for a node.
    Input: node name or 'all' for all nodes.
    """
    if node.strip().lower() == "all":
        promql = '(1 - node_filesystem_avail_bytes{mountpoint="/"} / node_filesystem_size_bytes{mountpoint="/"}) * 100'
    else:
        promql = f'(1 - node_filesystem_avail_bytes{{instance=~"{node.strip()}.*",mountpoint="/"}} / node_filesystem_size_bytes{{instance=~"{node.strip()}.*",mountpoint="/"}}) * 100'
    return _format_result(_query(promql))
