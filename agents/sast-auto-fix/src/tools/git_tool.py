"""
src/tools/git_tool.py — Git operations for the SAST Auto-Fixer.

OPERATIONS
──────────
  git_diff(repo_dir)              → unified diff of current changes
  git_create_branch(repo_dir, name) → create + checkout a fix branch
  git_commit(repo_dir, message)   → stage all changes + commit
  git_push(repo_dir, branch)      → push branch to origin
  git_current_branch(repo_dir)    → return current branch name
"""

from __future__ import annotations

import logging
import subprocess
from pathlib import Path

log = logging.getLogger(__name__)


def _run(cmd: list[str], cwd: str, check: bool = True) -> subprocess.CompletedProcess:
    log.debug("git %s (cwd=%s)", " ".join(cmd[1:]), cwd)
    return subprocess.run(
        cmd,
        cwd=cwd,
        capture_output=True,
        text=True,
        check=check,
    )


def git_diff(repo_dir: str) -> str:
    """
    Return the unified diff of all unstaged + staged changes in repo_dir.

    This is the patch that will be committed. If empty, nothing changed.
    """
    result = _run(["git", "diff", "HEAD"], cwd=repo_dir, check=False)
    diff = result.stdout.strip()
    if not diff:
        # Also check staged changes
        result = _run(["git", "diff", "--cached"], cwd=repo_dir, check=False)
        diff = result.stdout.strip()
    return diff or "(no changes)"


def git_create_branch(repo_dir: str, branch_name: str) -> str:
    """
    Create and checkout a new branch. Returns the branch name.

    If the branch already exists, checks it out.
    """
    # Try create + checkout
    result = _run(
        ["git", "checkout", "-b", branch_name],
        cwd=repo_dir,
        check=False,
    )
    if result.returncode != 0:
        # Branch exists — just check it out
        _run(["git", "checkout", branch_name], cwd=repo_dir)
        log.info("Checked out existing branch: %s", branch_name)
    else:
        log.info("Created branch: %s", branch_name)
    return branch_name


def git_commit(repo_dir: str, message: str) -> str:
    """
    Stage all changes and commit with message.

    Returns the short commit hash.
    """
    _run(["git", "add", "-A"], cwd=repo_dir)
    _run(["git", "commit", "-m", message], cwd=repo_dir)

    result = _run(["git", "rev-parse", "--short", "HEAD"], cwd=repo_dir)
    sha = result.stdout.strip()
    log.info("Committed: %s (%s)", message[:60], sha)
    return sha


def git_push(repo_dir: str, branch: str) -> bool:
    """
    Push branch to origin. Returns True on success.

    Uses --force-with-lease so stale remote fix branches (left over from a
    previous agent run) are overwritten safely without clobbering concurrent
    human pushes.
    """
    result = _run(
        ["git", "push", "--set-upstream", "--force", "origin", branch],
        cwd=repo_dir,
        check=False,
    )
    if result.returncode != 0:
        log.error("git push failed: %s", result.stderr.strip())
        return False
    log.info("Pushed branch %s to origin", branch)
    return True


def git_current_branch(repo_dir: str) -> str:
    """Return the name of the current branch."""
    result = _run(
        ["git", "rev-parse", "--abbrev-ref", "HEAD"],
        cwd=repo_dir,
        check=False,
    )
    return result.stdout.strip()


def git_init_if_needed(repo_dir: str, default_branch: str = "main") -> None:
    """
    Initialise a git repo in repo_dir if one doesn't exist already.
    Creates an initial commit so branches can be made.
    """
    repo = Path(repo_dir)
    if (repo / ".git").exists():
        return

    log.info("Initialising git repo in %s", repo_dir)
    _run(["git", "init", "-b", default_branch], cwd=repo_dir)
    _run(["git", "add", "-A"], cwd=repo_dir)
    _run(
        ["git", "commit", "-m", "chore: initial commit (deliberately vulnerable app)"],
        cwd=repo_dir,
    )
    log.info("Git repo initialised with initial commit")
