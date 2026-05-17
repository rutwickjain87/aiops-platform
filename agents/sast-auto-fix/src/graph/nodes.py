"""
src/graph/nodes.py — LangGraph node implementations for the SAST Auto-Fixer.

GRAPH FLOW
──────────
  scan → pick → read_ctx → fix → validate ──(pass)──→ open_pr → END
                                         ↑               │
                                         └──(fail+retry)─┘
                                         (fail+no retries) → END

NODES
─────
  scan       Runs Semgrep, populates findings[]
  pick       Selects the highest-severity finding
  read_ctx   Reads the vulnerable file for LLM context
  fix        LLM generates the fixed file + summary
  validate   Writes fix to disk, runs Docker tests, records diff
  open_pr    Commits, pushes branch, opens GitHub PR
"""

from __future__ import annotations

import hashlib
import logging
import os
import re
from pathlib import Path

from langchain_anthropic import ChatAnthropic
from langchain_core.messages import HumanMessage, SystemMessage

from src.graph.state import SastFixState
from src.tools.docker_tool import build_image, run_tests_in_docker
from src.tools.git_tool import (
    git_commit,
    git_create_branch,
    git_diff,
    git_init_if_needed,
)
from src.tools.github_tool import open_pr as _open_pr
from src.tools.semgrep_tool import format_findings_summary, run_semgrep

log = logging.getLogger(__name__)

FIX_MODEL = os.environ.get("FIX_MODEL", "claude-sonnet-4-6")


# ── Node: scan ────────────────────────────────────────────────────────────────

def scan(state: SastFixState) -> dict:
    """Run Semgrep against the target directory."""
    target_dir = state["target_dir"]
    log.info("scan: running Semgrep on %s", target_dir)

    # Ensure git repo exists (needed for diff + branch operations later)
    git_init_if_needed(target_dir)

    # Build Docker image once (cached on repeat runs)
    build_image(target_dir)

    findings = run_semgrep(target_dir)
    summary = format_findings_summary(findings)
    log.info("scan: %d findings\n%s", len(findings), summary)

    return {"findings": findings}


# ── Node: pick ────────────────────────────────────────────────────────────────

def pick(state: SastFixState) -> dict:
    """
    Select the highest-severity finding to fix.

    Strategy: take the first finding (already sorted ERROR > WARNING > INFO
    by run_semgrep). If no findings exist, mark final_status=no_findings.
    """
    findings = state["findings"]

    if not findings:
        log.info("pick: no findings — nothing to fix")
        return {"selected_finding": None, "final_status": "no_findings"}

    selected = findings[0]
    log.info(
        "pick: selected [%s] %s in %s line %d",
        selected["severity"], selected["rule_id"],
        selected["path"], selected["line"],
    )
    return {"selected_finding": selected}


# ── Node: read_ctx ────────────────────────────────────────────────────────────

def read_ctx(state: SastFixState) -> dict:
    """Read the full content of the vulnerable file."""
    finding = state["selected_finding"]
    if not finding:
        return {"file_content": ""}

    file_path = Path(state["target_dir"]) / finding["path"]
    try:
        content = file_path.read_text()
        log.info("read_ctx: read %d chars from %s", len(content), file_path)
        return {"file_content": content}
    except FileNotFoundError:
        log.error("read_ctx: file not found: %s", file_path)
        return {"file_content": f"[ERROR] File not found: {file_path}"}


# ── Helper: strip non-Python prefix ──────────────────────────────────────────

# Regex that matches the first character of a valid Python "starter" line:
#   - shebang (#!)
#   - comment (#)
#   - docstring (""" or ''')
#   - from / import
#   - class / def / async def
#   - __future__ and similar dunder-module-level assignments
_PYTHON_STARTER = re.compile(
    r"^(#|\"\"\"|\'\'\'"
    r"|from\s|import\s"
    r"|class\s|def\s|async\s"
    r"|__[a-zA-Z]+__\s*=)",
    re.MULTILINE,
)


def _strip_non_python_prefix(content: str) -> str:
    """
    Drop any leading prose/reasoning lines that the LLM emitted before the
    actual Python source code.  Works by finding the first line that looks
    like valid Python and discarding everything before it.

    Falls back to the original content if no Python starter is found.
    """
    match = _PYTHON_STARTER.search(content)
    if match and match.start() > 0:
        stripped = content[match.start():]
        log.warning(
            "_strip_non_python_prefix: removed %d leading chars of non-Python text",
            match.start(),
        )
        return stripped
    return content


# ── Node: fix ─────────────────────────────────────────────────────────────────

def fix(state: SastFixState) -> dict:
    """
    Ask the LLM to generate a secure fix for the selected finding.

    Returns the complete fixed file content (not a diff) so it can be
    written directly to disk. Also returns a one-paragraph fix_summary
    explaining what changed and why.

    On retry: the previous test_output is included so the LLM knows
    what went wrong and can adjust the fix.
    """
    finding = state["selected_finding"]
    retry = state["retry_count"]

    log.info("fix: generating fix (attempt %d)", retry + 1)

    retry_context = ""
    if retry > 0:
        retry_context = (
            f"\n\nPREVIOUS FIX FAILED (attempt {retry}):\n"
            f"The tests produced the following output:\n"
            f"```\n{state['test_output'][-2000:]}\n```\n"
            f"Adjust the fix so all tests pass."
        )

    llm = ChatAnthropic(model=FIX_MODEL, max_tokens=4096)
    messages = [
        SystemMessage(content=(
            "You are a senior application security engineer. Your job is to fix "
            "a security vulnerability identified by Semgrep without breaking any "
            "existing tests.\n\n"
            "CRITICAL OUTPUT RULES — violating these will break the pipeline:\n"
            "1. The VERY FIRST character of your response MUST be the first character "
            "of the fixed Python file (e.g. '#' for a comment or 'f' for 'from'). "
            "Do NOT write any explanation, reasoning, or prose before the file.\n"
            "2. No markdown fences (no ``` blocks).\n"
            "3. Preserve all existing functionality (the tests must still pass).\n"
            "4. Fix ONLY the identified vulnerability — do not refactor unrelated code.\n"
            "5. After the complete fixed file, add EXACTLY this separator on its own "
            "line: ---FIX_SUMMARY---\n"
            "   Then write a single paragraph explaining what you changed and why.\n\n"
            "OUTPUT FORMAT (follow exactly):\n"
            "<complete fixed Python file — starts with '#' or 'from' or 'import', "
            "NO preamble>\n"
            "---FIX_SUMMARY---\n"
            "<one paragraph: what changed and why>"
        )),
        HumanMessage(content=(
            f"VULNERABILITY FOUND BY SEMGREP\n"
            f"Rule    : {finding['rule_id']}\n"
            f"Severity: {finding['severity']}\n"
            f"File    : {finding['path']} (line {finding['line']})\n"
            f"Message : {finding['message']}\n\n"
            f"VULNERABLE CODE SNIPPET:\n{finding['code_snippet']}\n\n"
            f"FULL FILE CONTENT:\n{state['file_content']}"
            f"{retry_context}"
        )),
    ]

    response = llm.invoke(messages)
    raw = response.content.strip()

    # Parse out the fixed file content and summary
    if "---FIX_SUMMARY---" in raw:
        parts = raw.split("---FIX_SUMMARY---", 1)
        fixed_content = parts[0].strip()
        fix_summary = parts[1].strip()
    else:
        fixed_content = raw
        fix_summary = f"Fixed {finding['rule_id']} in {finding['path']}."

    # Strip any accidental markdown fences
    fixed_content = re.sub(r"^```[a-z]*\n?", "", fixed_content)
    fixed_content = re.sub(r"\n?```$", "", fixed_content)
    fixed_content = fixed_content.strip()

    # Strip any leading non-Python reasoning text the LLM may have emitted.
    # Python files legitimately start with: a shebang, a comment (#), an
    # import/from statement, a class/def, a docstring, or a __future__ import.
    fixed_content = _strip_non_python_prefix(fixed_content)

    # Generate branch name from rule_id hash
    rule_hash = hashlib.md5(
        finding["rule_id"].encode(), usedforsecurity=False
    ).hexdigest()[:6]
    branch_name = f"fix/sast-{rule_hash}-attempt{retry + 1}"

    log.info("fix: generated %d chars, branch=%s", len(fixed_content), branch_name)
    return {
        "fixed_content": fixed_content,
        "fix_summary": fix_summary,
        "branch_name": branch_name,
    }


# ── Node: validate ────────────────────────────────────────────────────────────

def validate(state: SastFixState) -> dict:
    """
    Write the fix to disk, capture the diff, then run tests in Docker.

    On test failure the retry_count is incremented — the graph's
    conditional edge will route back to fix if retries remain.
    """
    finding = state["selected_finding"]
    file_path = Path(state["target_dir"]) / finding["path"]
    target_dir = state["target_dir"]

    log.info("validate: writing fix to %s", file_path)

    # Create fix branch
    git_create_branch(target_dir, state["branch_name"])

    # Write the fixed file
    file_path.write_text(state["fixed_content"])

    # Capture diff (against HEAD — shows what changed vs the original commit)
    diff = git_diff(target_dir)
    log.info("validate: diff is %d chars", len(diff))
    if diff == "(no changes)":
        log.warning("validate: diff is empty — fixed content may be identical to original")

    # Run tests in Docker sandbox
    test_result = run_tests_in_docker(target_dir)
    log.info(
        "validate: tests %s (exit %d)",
        "PASSED" if test_result.passed else "FAILED",
        test_result.exit_code,
    )

    return {
        "diff": diff,
        "test_output": test_result.output,
        "test_passed": test_result.passed,
        "retry_count": state["retry_count"] + (0 if test_result.passed else 1),
    }


# ── Node: open_pr ─────────────────────────────────────────────────────────────

def open_pr(state: SastFixState) -> dict:
    """
    Commit the fix, push the branch, and open a GitHub PR.

    Falls back to local diff output if GITHUB_TOKEN / PR_REPO are not set.
    """
    finding = state["selected_finding"]
    target_dir = state["target_dir"]
    branch = state["branch_name"]

    commit_msg = (
        f"fix(sast): {finding['rule_id']} in {finding['path']}\n\n"
        f"{state['fix_summary']}\n\n"
        f"Semgrep rule: {finding['rule_id']}\n"
        f"CWE: see rule documentation"
    )

    sha = git_commit(target_dir, commit_msg)
    log.info("open_pr: committed %s", sha)

    pr_result = _open_pr(
        repo_dir=target_dir,
        branch=branch,
        finding=finding,
        fix_summary=state["fix_summary"],
        diff=state["diff"],
    )

    final_status = "pr_opened" if pr_result.opened else "diff_only"
    log.info("open_pr: status=%s url=%s", final_status, pr_result.url)

    return {
        "pr_url": pr_result.url,
        "final_status": final_status,
    }


# ── Routing function ──────────────────────────────────────────────────────────

def route_after_validate(state: SastFixState) -> str:
    """
    Conditional edge after validate:
      - tests passed           → open_pr
      - tests failed, retries left → fix (retry)
      - tests failed, no retries → end_failed
    """
    if state["test_passed"]:
        return "open_pr"
    if state["retry_count"] < state["max_retries"]:
        log.info(
            "route: tests failed, retrying (attempt %d/%d)",
            state["retry_count"], state["max_retries"],
        )
        return "fix"
    log.warning("route: tests failed after %d retries — stopping", state["max_retries"])
    return "end_failed"


def end_failed(state: SastFixState) -> dict:
    """Terminal node when all retries are exhausted."""
    log.error(
        "end_failed: could not fix %s after %d attempts",
        state.get("selected_finding", {}).get("rule_id", "unknown"),
        state["retry_count"],
    )
    return {"final_status": "failed"}
