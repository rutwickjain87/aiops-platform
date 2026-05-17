"""
src/tools/semgrep_tool.py — Semgrep scanner wrapper.

Runs Semgrep against a target directory and returns structured findings
sorted by severity. Requires semgrep to be installed:
    pip install semgrep

SEMGREP RULES USED
──────────────────
  p/python   — general Python security rules (includes CWE-78, 89, 22, 95, 798)

HOW IT WORKS
────────────
Semgrep emits JSON on stdout. Each finding has:
  - path       : file path relative to target dir
  - start.line : line number of the vulnerability
  - rule_id    : e.g. "python.lang.security.audit.subprocess-shell-true"
  - severity   : ERROR | WARNING | INFO
  - message    : human-readable explanation
  - extra.lines: the vulnerable code snippet
"""

from __future__ import annotations

import json
import logging
import shlex
import subprocess
import sys
from pathlib import Path


def _semgrep_bin() -> str:
    """
    Return the path to the semgrep binary.

    Prefers the binary in the same venv as the running Python so it works
    without semgrep being on the system PATH.
    """
    venv_semgrep = Path(sys.executable).parent / "semgrep"
    if venv_semgrep.exists():
        return str(venv_semgrep)
    return "semgrep"  # fall back to system PATH

log = logging.getLogger(__name__)

# Severity order for sorting (higher = more critical)
_SEVERITY_ORDER = {"ERROR": 3, "WARNING": 2, "INFO": 1}


def run_semgrep(target_dir: str, ruleset: str = "p/python") -> list[dict]:
    """
    Run Semgrep against target_dir and return findings sorted by severity.

    Args:
        target_dir: Absolute path to the directory to scan.
        ruleset:    Semgrep ruleset identifier (default: p/python).

    Returns:
        List of finding dicts, each with keys:
          rule_id, severity, path, line, message, code_snippet
        Sorted: ERROR first, then WARNING, then INFO.
        Empty list if no findings or semgrep not installed.
    """
    target = Path(target_dir).resolve()
    if not target.exists():
        log.error("Target directory does not exist: %s", target)
        return []

    cmd = [
        _semgrep_bin(),
        "--config", ruleset,
        "--json",
        "--quiet",
        str(target),
    ]

    log.info("Running: %s", shlex.join(cmd))

    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=120,
        )
    except FileNotFoundError:
        log.error(
            "semgrep not found — run: cd agents/sast-auto-fix && uv pip install semgrep --python .venv/bin/python"
        )
        return []
    except subprocess.TimeoutExpired:
        log.error("semgrep timed out after 120s")
        return []

    if result.returncode not in (0, 1):
        # 0 = no findings, 1 = findings found — both are fine
        # anything else is an error
        log.error("semgrep error (exit %d): %s", result.returncode, result.stderr[:500])
        return []

    try:
        data = json.loads(result.stdout)
    except json.JSONDecodeError as exc:
        log.error("Failed to parse semgrep JSON output: %s", exc)
        return []

    raw_findings = data.get("results", [])
    log.info("semgrep found %d findings in %s", len(raw_findings), target)

    findings = []
    for f in raw_findings:
        findings.append({
            "rule_id":      f.get("check_id", "unknown"),
            "severity":     f.get("extra", {}).get("severity", "WARNING"),
            "path":         f.get("path", ""),
            "line":         f.get("start", {}).get("line", 0),
            "message":      f.get("extra", {}).get("message", ""),
            "code_snippet": f.get("extra", {}).get("lines", ""),
        })

    # Sort: ERROR > WARNING > INFO
    findings.sort(
        key=lambda x: _SEVERITY_ORDER.get(x["severity"], 0),
        reverse=True,
    )
    return findings


def format_findings_summary(findings: list[dict]) -> str:
    """Return a human-readable summary of findings for LLM context."""
    if not findings:
        return "No findings."
    lines = [f"Semgrep found {len(findings)} finding(s):\n"]
    for i, f in enumerate(findings, 1):
        lines.append(
            f"{i}. [{f['severity']}] {f['rule_id']}\n"
            f"   File: {f['path']} line {f['line']}\n"
            f"   {f['message']}\n"
            f"   Code: {f['code_snippet'].strip()}\n"
        )
    return "\n".join(lines)
