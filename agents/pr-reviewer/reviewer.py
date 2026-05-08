"""
reviewer.py — CLI entry point for the PR Security Reviewer agent.

USAGE
─────
# Dry-run: print the review to stdout, don't post to GitHub
python reviewer.py --repo rutwickjain87/aiops-platform --pr 7

# Post (or update) the review as a GitHub PR comment
python reviewer.py --repo rutwickjain87/aiops-platform --pr 7 --post-comment

# Use a specific model
python reviewer.py --repo rutwickjain87/aiops-platform --pr 7 --model claude-sonnet-4-6

# Quiet mode (suppress step-by-step trace)
python reviewer.py --repo rutwickjain87/aiops-platform --pr 7 --quiet

ENVIRONMENT VARIABLES
─────────────────────
  ANTHROPIC_API_KEY   Required. Anthropic API key for the LLM.
  GITHUB_TOKEN        Required when --post-comment is set, or always (fetch_pr_diff
                      needs it to read private repos).

GITHUB ACTIONS
──────────────
In CI the workflow injects these via secrets:
  env:
    GITHUB_TOKEN: ${{ secrets.GITHUB_TOKEN }}
    ANTHROPIC_API_KEY: ${{ secrets.ANTHROPIC_API_KEY }}

The workflow calls:
  python reviewer.py --repo $REPO --pr $PR_NUMBER --post-comment
"""
from __future__ import annotations

import argparse
import sys

from planner import PRReviewerPlanner, ReviewerConfig


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="AI-powered PR security reviewer (Day 4 — aiops-platform)",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    p.add_argument(
        "--repo",
        required=True,
        metavar="OWNER/REPO",
        help="GitHub repository (e.g. rutwickjain87/aiops-platform)",
    )
    p.add_argument(
        "--pr",
        required=True,
        type=int,
        metavar="NUMBER",
        help="Pull request number to review",
    )
    p.add_argument(
        "--post-comment",
        action="store_true",
        default=False,
        help="Post (or update) the review as a GitHub PR comment",
    )
    p.add_argument(
        "--model",
        default="claude-haiku-4-5-20251001",
        metavar="MODEL",
        help="Anthropic model slug (default: claude-haiku-4-5-20251001)",
    )
    p.add_argument(
        "--quiet",
        action="store_true",
        default=False,
        help="Suppress per-step verbose trace",
    )
    return p.parse_args()


def main() -> None:
    args = parse_args()

    cfg = ReviewerConfig(
        model=args.model,
        verbose=not args.quiet,
    )
    planner = PRReviewerPlanner(config=cfg)

    print(f"\n{'=' * 60}")
    print(f"  PR Security Reviewer — {args.repo} PR #{args.pr}")
    print(f"  Model : {args.model}")
    print(f"  Post  : {'yes' if args.post_comment else 'dry-run (no comment posted)'}")
    print(f"{'=' * 60}\n")

    try:
        review = planner.run(
            repo=args.repo,
            pr_number=args.pr,
            post_comment=args.post_comment,
        )
    except RuntimeError as e:
        print(f"\n[ERROR] {e}", file=sys.stderr)
        sys.exit(1)

    print("\n" + "=" * 60)
    print("  REVIEW OUTPUT")
    print("=" * 60)
    print(review)
    print("=" * 60 + "\n")


if __name__ == "__main__":
    main()
