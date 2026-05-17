"""
src/graph/state.py — LangGraph state shape for the SAST Auto-Fixer.

STATE LIFECYCLE
───────────────
  CLI input:
    target_dir     → absolute path to the vulnerable app
    max_retries    → max fix retry attempts (default: 2)

  scan node:
    findings[]     → list of Semgrep finding dicts

  pick node:
    selected_finding → the highest-severity finding to fix

  read_ctx node:
    file_content   → full source of the vulnerable file

  fix node:
    fixed_content  → LLM-generated fixed version of the file
    fix_summary    → LLM one-paragraph explanation of the fix
    branch_name    → git branch name for this fix

  validate node:
    diff           → git diff of the change
    test_output    → Docker test output
    test_passed    → bool
    retry_count    → incremented on each failed attempt

  open_pr node:
    pr_url         → GitHub PR URL (empty if local-only mode)
    final_status   → "pr_opened" | "diff_only" | "failed" | "no_findings"
"""

from __future__ import annotations

from typing import Annotated

from langgraph.graph.message import add_messages
from typing_extensions import TypedDict


class SastFixState(TypedDict):
    # ── Input ─────────────────────────────────────────────────────────────────
    target_dir: str               # absolute path to the target app
    max_retries: int              # max fix attempts before giving up (default: 2)

    # ── scan node ─────────────────────────────────────────────────────────────
    findings: list[dict]          # all Semgrep findings, sorted by severity

    # ── pick node ─────────────────────────────────────────────────────────────
    selected_finding: dict | None  # the single finding we will fix

    # ── read_ctx node ─────────────────────────────────────────────────────────
    file_content: str             # full source of the vulnerable file

    # ── fix node ──────────────────────────────────────────────────────────────
    fixed_content: str            # LLM-generated fixed file content
    fix_summary: str              # LLM explanation of what was changed and why
    branch_name: str              # git branch for this fix

    # ── validate node ─────────────────────────────────────────────────────────
    diff: str                     # git diff of the applied fix
    test_output: str              # Docker sandbox test results
    test_passed: bool             # True if all tests passed
    retry_count: int              # number of fix retries so far

    # ── open_pr node ──────────────────────────────────────────────────────────
    pr_url: str                   # GitHub PR URL ("" in local-only mode)
    final_status: str             # "pr_opened" | "diff_only" | "failed" | "no_findings"

    # ── LangGraph message history ──────────────────────────────────────────────
    messages: Annotated[list, add_messages]


def initial_state(target_dir: str, max_retries: int = 2) -> SastFixState:
    """Build the initial state from CLI inputs."""
    return SastFixState(
        target_dir=target_dir,
        max_retries=max_retries,
        findings=[],
        selected_finding=None,
        file_content="",
        fixed_content="",
        fix_summary="",
        branch_name="",
        diff="",
        test_output="",
        test_passed=False,
        retry_count=0,
        pr_url="",
        final_status="",
        messages=[],
    )
