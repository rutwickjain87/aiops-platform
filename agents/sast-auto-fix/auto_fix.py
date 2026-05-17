"""
auto_fix.py — CLI entry point for the SAST Auto-Fixer LangGraph agent.

USAGE
─────
# Fix the highest-severity finding in the default target
python auto_fix.py

# Fix a specific target directory
python auto_fix.py --target /path/to/your/app

# Increase retry limit (default: 2)
python auto_fix.py --max-retries 3

# Dry run — scan only, do not fix
python auto_fix.py --scan-only

# Use a different model
python auto_fix.py --model claude-haiku-4-5-20251001

ENVIRONMENT VARIABLES
─────────────────────
  ANTHROPIC_API_KEY   Required. Powers the fix node LLM.
  GITHUB_TOKEN        Required for real PRs (repo scope).
  PR_REPO             GitHub repo for PRs (e.g. rutwickjain87/sast-lab).
  FIX_MODEL           Override the LLM model (default: claude-sonnet-4-6).
  LANGSMITH_TRACING   Set to "true" for LangSmith traces.
  LANGSMITH_PROJECT   LangSmith project name (default: sast-auto-fix).
"""

from __future__ import annotations

import argparse
import logging
import os
import sys
import time
from pathlib import Path

from dotenv import load_dotenv

load_dotenv(Path(__file__).parent / ".env")

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
log = logging.getLogger("auto_fix")

DEFAULT_TARGET = str(Path(__file__).parent / "targets" / "vulnerable_app")


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="SAST Auto-Fixer — scan, fix, validate, and PR security findings",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    p.add_argument(
        "--target", "-t",
        default=DEFAULT_TARGET,
        help=f"Path to the target app directory (default: {DEFAULT_TARGET})",
    )
    p.add_argument(
        "--max-retries",
        type=int,
        default=2,
        help="Max fix retry attempts before giving up (default: 2)",
    )
    p.add_argument(
        "--scan-only",
        action="store_true",
        help="Run Semgrep scan only — do not fix or open PR",
    )
    p.add_argument(
        "--model",
        default=None,
        help="Override FIX_MODEL env var",
    )
    return p.parse_args()


def main() -> None:
    args = parse_args()

    if args.model:
        os.environ["FIX_MODEL"] = args.model

    target_dir = str(Path(args.target).resolve())

    if not Path(target_dir).exists():
        log.error("Target directory does not exist: %s", target_dir)
        sys.exit(1)

    fix_model = os.environ.get("FIX_MODEL", "claude-sonnet-4-6")
    pr_repo = os.environ.get("PR_REPO", "(not set — local diff mode)")

    print(f"\n{'=' * 60}")
    print("  SAST Auto-Fixer")
    print(f"{'=' * 60}")
    print(f"  Target      : {target_dir}")
    print(f"  Max retries : {args.max_retries}")
    print(f"  Fix model   : {fix_model}")
    print(f"  PR repo     : {pr_repo}")
    print(f"  Scan only   : {args.scan_only}")
    print(f"  Tracing     : {os.environ.get('LANGSMITH_TRACING', 'false')}")
    print(f"{'=' * 60}\n")

    # ── Scan-only mode ─────────────────────────────────────────────────────────
    if args.scan_only:
        from src.tools.semgrep_tool import format_findings_summary, run_semgrep
        print("▶ Scan only mode — running Semgrep...\n")
        findings = run_semgrep(target_dir)
        print(format_findings_summary(findings))
        print(f"Found {len(findings)} finding(s). Run without --scan-only to fix.")
        return

    # ── Full agent run ─────────────────────────────────────────────────────────
    from src.graph.graph import sast_fix_graph
    from src.graph.state import initial_state

    state = initial_state(
        target_dir=target_dir,
        max_retries=args.max_retries,
    )

    print("▶ Running: scan → pick → read_ctx → fix → validate → open_pr\n")
    start = time.time()

    try:
        result = sast_fix_graph.invoke(state)
    except KeyboardInterrupt:
        print("\n[Interrupted]")
        sys.exit(0)
    except Exception as exc:
        log.exception("Graph execution failed: %s", exc)
        sys.exit(1)

    elapsed = time.time() - start
    final_status = result.get("final_status", "unknown")

    print(f"\n{'=' * 60}")
    print("  RESULT")
    print(f"{'=' * 60}")

    if final_status == "no_findings":
        print("  ✅ No findings — target is clean!")

    elif final_status == "pr_opened":
        print(f"  ✅ PR opened: {result.get('pr_url')}")
        print(f"  Branch     : {result.get('branch_name')}")
        print(f"  Finding    : {result['selected_finding']['rule_id']}")

    elif final_status == "diff_only":
        print("  ✅ Fix applied and branch pushed (PR creation failed — see above)")
        print(f"  Branch : {result.get('branch_name')}")
        print(f"  Finding: {result['selected_finding']['rule_id']}")
        print(f"  Create PR manually: https://github.com/{os.environ.get('PR_REPO', 'OWNER/REPO')}/compare/{result.get('branch_name')}")

    elif final_status == "failed":
        print(f"  ❌ Fix failed after {result.get('retry_count', 0)} attempt(s)")
        print(f"  Finding: {result['selected_finding']['rule_id']}")
        print(f"\n  Last test output:\n{result.get('test_output', '')[-1000:]}")

    print(f"\n  Completed in {elapsed:.1f}s")
    print(f"{'=' * 60}\n")


if __name__ == "__main__":
    main()
