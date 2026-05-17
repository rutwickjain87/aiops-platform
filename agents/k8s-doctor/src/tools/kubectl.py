"""
src/tools/kubectl.py — kubectl wrapper tools for the K8s Doctor agent.

All tools are read-only by default (--dry-run where applicable).
Each returns a plain string so the LLM can consume it directly.

TOOLS
─────
  kubectl_describe(resource, namespace, context)  → describe output
  kubectl_logs(resource, namespace, context)      → last N log lines
  kubectl_events(namespace, context)              → recent warning events
  kubectl_get_pods(namespace, context)            → pod list with status

SAFETY
──────
These tools only run kubectl get / describe / logs — no mutations.
Day 7 adds --apply flag gated behind explicit human approval.
"""

from __future__ import annotations

import subprocess
import shlex
import logging

log = logging.getLogger(__name__)

# Default context — override via env or CLI flag
DEFAULT_CONTEXT = "kind-doctor-lab"
DEFAULT_TIMEOUT = 15  # seconds


def _run(cmd: list[str], timeout: int = DEFAULT_TIMEOUT) -> str:
    """Run a kubectl command and return stdout + stderr combined."""
    log.debug("Running: %s", shlex.join(cmd))
    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
        output = result.stdout.strip()
        if result.returncode != 0:
            stderr = result.stderr.strip()
            return f"[kubectl exit {result.returncode}]\n{stderr or output}"
        return output or "(no output)"
    except subprocess.TimeoutExpired:
        return f"[ERROR] kubectl timed out after {timeout}s"
    except FileNotFoundError:
        return "[ERROR] kubectl not found — install kubectl and ensure it is on PATH"


def kubectl_describe(
    resource: str,
    namespace: str,
    resource_type: str = "deployment",
    context: str = DEFAULT_CONTEXT,
) -> str:
    """
    Run `kubectl describe <type> <resource> -n <namespace>`.

    Returns the full describe output which includes: events, status conditions,
    container spec, image, resource limits, and restart count.
    This is usually the single most useful tool for diagnosing pod failures.

    Args:
        resource:      Name of the resource (e.g. "crashloop-demo")
        namespace:     Kubernetes namespace (e.g. "doctor-lab")
        resource_type: Resource kind — "deployment", "pod", "replicaset" (default: "deployment")
        context:       kubectl context (default: kind-doctor-lab)
    """
    cmd = [
        "kubectl", "describe", resource_type, resource,
        "-n", namespace,
        "--context", context,
    ]
    return _run(cmd)


def kubectl_logs(
    resource: str,
    namespace: str,
    tail: int = 50,
    previous: bool = False,
    context: str = DEFAULT_CONTEXT,
) -> str:
    """
    Run `kubectl logs deployment/<resource> -n <namespace> --tail=N`.

    Returns the last N log lines from the pod's main container.
    Use previous=True to see logs from the previously crashed container,
    which is essential for CrashLoopBackOff diagnosis.

    Args:
        resource:   Deployment name (e.g. "crashloop-demo")
        namespace:  Kubernetes namespace
        tail:       Number of log lines to return (default: 50)
        previous:   If True, fetch logs from the previously terminated container
        context:    kubectl context
    """
    cmd = [
        "kubectl", "logs", f"deployment/{resource}",
        "-n", namespace,
        f"--tail={tail}",
        "--context", context,
    ]
    if previous:
        cmd.append("--previous")
    return _run(cmd)


def kubectl_events(
    namespace: str,
    context: str = DEFAULT_CONTEXT,
    field_selector: str = "type=Warning",
) -> str:
    """
    Run `kubectl get events -n <namespace> --field-selector type=Warning`.

    Returns warning events sorted by time. This is the fastest way to see
    BackOff, Failed, Unhealthy, and OOMKilled events for all resources
    in the namespace at once.

    Args:
        namespace:       Kubernetes namespace
        context:         kubectl context
        field_selector:  Filter events (default: Warning events only)
    """
    cmd = [
        "kubectl", "get", "events",
        "-n", namespace,
        f"--field-selector={field_selector}",
        "--sort-by=.lastTimestamp",
        "--context", context,
    ]
    return _run(cmd)


def kubectl_get_pods(
    namespace: str,
    context: str = DEFAULT_CONTEXT,
    label_selector: str = "",
) -> str:
    """
    Run `kubectl get pods -n <namespace> -o wide`.

    Returns pod list with STATUS, RESTARTS, AGE, NODE, and IP columns.
    High RESTARTS count immediately signals CrashLoopBackOff.

    Args:
        namespace:       Kubernetes namespace
        context:         kubectl context
        label_selector:  Optional -l filter (e.g. "app=crashloop-demo")
    """
    cmd = [
        "kubectl", "get", "pods",
        "-n", namespace,
        "-o", "wide",
        "--context", context,
    ]
    if label_selector:
        cmd += ["-l", label_selector]
    return _run(cmd)
