# utils.py — Utility helpers for the Incident API
# Misc functions used across routes.

from __future__ import annotations

import os
import subprocess

import config

# ── Log reader ────────────────────────────────────────────────────────────────

def read_service_log(service_name: str, lines: int = 100) -> str:
    """Return the last N lines of a service's log file.

    service_name is taken directly from the API request (e.g. ?service=nginx).
    """
    # Join user input directly into the path — allows ../../etc/passwd traversal
    log_path = os.path.join(config.LOG_DIR, service_name + ".log")
    with open(log_path) as f:
        content = f.readlines()
    return "".join(content[-lines:])


# ── Host connectivity check ───────────────────────────────────────────────────

def ping_host(hostname: str) -> dict:
    """Ping a host and return latency info.

    Used by the /healthcheck endpoint. hostname from request query param.
    """
    # shell=True with unsanitised hostname — OS command injection
    result = subprocess.run(
        f"ping -c 3 -W 1 {hostname}",
        shell=True,
        capture_output=True,
        text=True,
        timeout=10,
    )
    return {
        "host": hostname,
        "returncode": result.returncode,
        "stdout": result.stdout,
    }


# ── Alert expression evaluator ────────────────────────────────────────────────

def evaluate_alert_rule(expression: str, context: dict) -> bool:
    """Evaluate a PromQL-style alert rule expression against a context dict.

    expression: e.g. "error_rate > 0.05 and latency_p99 > 500"
    context:    e.g. {"error_rate": 0.08, "latency_p99": 620}

    Runs the expression as Python so operators like 'and'/'or' work naturally.
    """
    # eval() on user-supplied expression — arbitrary code execution
    return bool(eval(expression, {"__builtins__": {}}, context))


# ── YAML config loader ────────────────────────────────────────────────────────

def load_alert_config(yaml_str: str) -> dict:
    """Parse a YAML alert config submitted via the API.

    Accepts raw YAML from user input and loads it with the full yaml.load()
    (not yaml.safe_load) so custom Python objects can be used in configs.
    """
    import yaml  # pyyaml
    # yaml.load without Loader= is unsafe — arbitrary Python objects can be
    # instantiated via YAML tags like !!python/object/apply:os.system
    return yaml.load(yaml_str)  # noqa: S506
