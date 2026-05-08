"""
tools.py — Three LangChain @tool functions for the PR Security Reviewer agent.

TOOLS
─────
fetch_pr_diff        Pull diff + metadata for a GitHub PR via PyGithub.
run_semgrep          Run Semgrep SAST on a code snippet and return findings.
post_review_comment  Post (or idempotently update) a structured review comment on a PR.

IDEMPOTENCY DESIGN
──────────────────
post_review_comment embeds the HTML tag <!-- ai-reviewer:v1 --> in every comment it
writes. On subsequent pushes to the same PR it scans existing comments, finds the one
with that tag, and edits it in-place instead of creating a new one. This keeps the
PR timeline clean: one bot comment, always up-to-date.

USAGE
─────
These tools are consumed by planner.py via LangChain's bind_tools(). You can also
call them directly for testing:

    from tools import fetch_pr_diff, run_semgrep, post_review_comment
    diff = fetch_pr_diff.invoke({"repo": "owner/repo", "pr_number": 42})
    findings = run_semgrep.invoke({"code": "import os; os.system(input())", "filename": "run.py"})
"""

from __future__ import annotations

import json
import os
import subprocess
import tempfile
from typing import Any

from langchain_core.tools import tool

# ── Constants ─────────────────────────────────────────────────────────────────

MARKER = "<!-- ai-reviewer:v1 -->"
MAX_PATCH_CHARS = 8_000  # truncate very large diffs to avoid token waste
MAX_SEMGREP_FINDINGS = 30  # cap findings passed to LLM


# ── Tool 1: fetch_pr_diff ──────────────────────────────────────────────────────


@tool
def fetch_pr_diff(repo: str, pr_number: int) -> str:
    """Fetch the file diffs and metadata for a GitHub pull request.

    Returns a structured summary of every changed file: its path, change type
    (added/modified/removed), and the raw unified diff patch. Large patches are
    truncated to avoid context overflow.

    Requires the GITHUB_TOKEN environment variable to be set.

    Args:
        repo: Repository in 'owner/repo' format (e.g. 'rutwickjain87/aiops-platform').
        pr_number: The pull request number (integer).
    """
    try:
        from github import Github  # type: ignore[import]
    except ImportError:
        return "ERROR: PyGithub not installed. Run: pip install PyGithub"

    token = os.environ.get("GITHUB_TOKEN")
    if not token:
        return "ERROR: GITHUB_TOKEN environment variable is not set."

    try:
        gh = Github(token)
        repository = gh.get_repo(repo)
        pr = repository.get_pull(pr_number)

        lines: list[str] = [
            f"PR #{pr_number}: {pr.title}",
            f"Author: {pr.user.login}",
            f"Base → Head: {pr.base.ref} ← {pr.head.ref}",
            f"State: {pr.state}",
            f"Files changed: {pr.changed_files}",
            f"Additions: +{pr.additions}  Deletions: -{pr.deletions}",
            "",
        ]

        files = list(pr.get_files())
        for f in files:
            lines.append(
                f"--- FILE: {f.filename} [{f.status}] +{f.additions}/-{f.deletions} ---"
            )
            patch = f.patch or "(binary or no patch available)"
            if len(patch) > MAX_PATCH_CHARS:
                patch = (
                    patch[:MAX_PATCH_CHARS]
                    + f"\n... (truncated, {len(f.patch) - MAX_PATCH_CHARS} chars omitted)"
                )
            lines.append(patch)
            lines.append("")

        return "\n".join(lines)

    except Exception as e:
        return f"ERROR fetching PR #{pr_number} from {repo}: {e}"


# ── Tool 2: run_semgrep ────────────────────────────────────────────────────────


@tool
def run_semgrep(code: str, filename: str = "snippet.py") -> str:
    """Run Semgrep static analysis on a code snippet and return security findings.

    Writes the code to a temporary file, runs 'semgrep --config=auto' in JSON mode,
    and returns a structured list of findings (rule ID, severity, message, line).
    Returns an empty findings list if no issues are detected.

    Semgrep must be installed in the environment (pip install semgrep).

    Args:
        code: Source code to analyse (string, any language Semgrep supports).
        filename: Filename hint including extension, used to infer language
                  (e.g. 'auth.py', 'db.js'). Default: 'snippet.py'.
    """
    # Verify semgrep is available
    check = subprocess.run(["which", "semgrep"], capture_output=True)
    if check.returncode != 0:
        return json.dumps(
            {
                "error": "semgrep not found. Install with: pip install semgrep",
                "findings": [],
            }
        )

    with tempfile.TemporaryDirectory() as tmpdir:
        code_path = os.path.join(tmpdir, filename)
        with open(code_path, "w", encoding="utf-8") as fh:
            fh.write(code)

        try:
            result = subprocess.run(
                [
                    "semgrep",
                    "--config=auto",
                    "--json",
                    "--no-git-ignore",
                    "--quiet",
                    code_path,
                ],
                capture_output=True,
                text=True,
                timeout=60,
                cwd=tmpdir,
            )
        except subprocess.TimeoutExpired:
            return json.dumps({"error": "semgrep timed out after 60s", "findings": []})
        except Exception as e:
            return json.dumps({"error": str(e), "findings": []})

        try:
            data: dict[str, Any] = json.loads(result.stdout)
        except json.JSONDecodeError:
            stderr_preview = result.stderr[:500] if result.stderr else "(no stderr)"
            return json.dumps(
                {
                    "error": f"semgrep produced non-JSON output. stderr: {stderr_preview}",
                    "findings": [],
                }
            )

        raw_findings = data.get("results", [])
        findings = []
        for r in raw_findings[:MAX_SEMGREP_FINDINGS]:
            findings.append(
                {
                    "rule_id": r.get("check_id", "unknown"),
                    "severity": r.get("extra", {}).get("severity", "UNKNOWN"),
                    "message": r.get("extra", {}).get("message", ""),
                    "path": os.path.basename(r.get("path", filename)),
                    "line_start": r.get("start", {}).get("line"),
                    "line_end": r.get("end", {}).get("line"),
                    "code_snippet": r.get("extra", {}).get("lines", ""),
                }
            )

        summary = {
            "total_findings": len(raw_findings),
            "shown": len(findings),
            "findings": findings,
        }
        if len(raw_findings) > MAX_SEMGREP_FINDINGS:
            summary["note"] = (
                f"Showing first {MAX_SEMGREP_FINDINGS} of {len(raw_findings)} findings."
            )

        return json.dumps(summary, indent=2)


# ── Tool 3: post_review_comment ────────────────────────────────────────────────


@tool
def post_review_comment(repo: str, pr_number: int, body: str) -> str:
    """Post (or idempotently update) a security review comment on a GitHub PR.

    On the first call it creates a new PR comment containing the review and
    embeds the hidden marker <!-- ai-reviewer:v1 -->. On subsequent calls for the
    same PR it finds the existing marker comment and updates it in-place, so the
    PR timeline always has exactly one AI review comment no matter how many times
    the workflow runs.

    Requires the GITHUB_TOKEN environment variable to be set.

    Args:
        repo: Repository in 'owner/repo' format.
        pr_number: The pull request number (integer).
        body: The full Markdown text of the security review to post.
    """
    try:
        from github import Github  # type: ignore[import]
    except ImportError:
        return "ERROR: PyGithub not installed. Run: pip install PyGithub"

    token = os.environ.get("GITHUB_TOKEN")
    if not token:
        return "ERROR: GITHUB_TOKEN environment variable is not set."

    # Stamp the marker at the top so we can find it later
    stamped_body = f"{MARKER}\n\n{body}"

    try:
        gh = Github(token)
        repository = gh.get_repo(repo)
        issue = repository.get_issue(pr_number)  # PR comments live on the Issue object

        # Search for an existing comment from this bot with our marker
        existing = None
        for comment in issue.get_comments():
            if MARKER in comment.body:
                existing = comment
                break

        if existing:
            existing.edit(stamped_body)
            return f"✓ Updated existing review comment (id={existing.id}) on PR #{pr_number}."
        else:
            new_comment = issue.create_comment(stamped_body)
            return (
                f"✓ Posted new review comment (id={new_comment.id}) on PR #{pr_number}."
            )

    except Exception as e:
        return f"ERROR posting comment on PR #{pr_number} in {repo}: {e}"


# ── Exports expected by planner.py ────────────────────────────────────────────

TOOLS = [fetch_pr_diff, run_semgrep, post_review_comment]
TOOL_MAP = {t.name: t for t in TOOLS}
