"""
generate.py — CLI entry point for the IaC Generator LangGraph agent.

USAGE
─────
# Interactive: describe your infrastructure, get Terraform files
python generate.py "A containerised web app on AWS with ALB and Postgres RDS"

# Specify output directory
python generate.py "ECS Fargate app with Redis cache" --output ./infra

# Skip terraform validate (faster, for iteration)
python generate.py "Simple S3 static site with CloudFront" --no-validate

# Increase retry attempts (default: 2)
python generate.py "Full production setup" --max-retries 3

ENVIRONMENT VARIABLES
─────────────────────
  ANTHROPIC_API_KEY   Required. Powers the clarify/plan/generate nodes.
  IAC_MODEL           Override LLM model (default: claude-sonnet-4-6).
  LANGSMITH_TRACING   Set to "true" for LangSmith traces.
  LANGSMITH_PROJECT   LangSmith project name (default: iac-generator).
"""

from __future__ import annotations

import argparse
import logging
import os
import sys
import time
from pathlib import Path

from dotenv import load_dotenv

load_dotenv(Path(__file__).parent / ".env", override=True)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
log = logging.getLogger("generate")

DEFAULT_OUTPUT = str(Path.cwd() / "iac-output")


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="IaC Generator — describe infrastructure, get Terraform",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    p.add_argument(
        "prompt",
        nargs="?",
        help="Natural-language infrastructure description. Reads from stdin if omitted.",
    )
    p.add_argument(
        "--output", "-o",
        default=DEFAULT_OUTPUT,
        help=f"Directory to write .tf files (default: {DEFAULT_OUTPUT})",
    )
    p.add_argument(
        "--max-retries",
        type=int,
        default=2,
        help="Max terraform validate retry attempts (default: 2)",
    )
    p.add_argument(
        "--no-validate",
        action="store_true",
        help="Skip terraform validate (generate files only)",
    )
    p.add_argument(
        "--model",
        default=None,
        help="Override LLM model (default: claude-sonnet-4-6)",
    )
    return p.parse_args()


def main() -> None:
    args = parse_args()

    if not os.environ.get("ANTHROPIC_API_KEY"):
        print("❌  ANTHROPIC_API_KEY not set. Add it to agents/iac-generator/.env")
        sys.exit(1)

    if args.model:
        os.environ["IAC_MODEL"] = args.model

    # Get prompt from arg or stdin
    prompt = args.prompt
    if not prompt:
        if sys.stdin.isatty():
            print("Describe your infrastructure (Ctrl+D when done):")
        prompt = sys.stdin.read().strip()
    if not prompt:
        print("❌  No prompt provided. Pass a description as argument or via stdin.")
        sys.exit(1)

    # Optionally skip validation by setting max_retries=0 and patching validate node
    if args.no_validate:
        os.environ["IAC_SKIP_VALIDATE"] = "1"

    print()
    print("=" * 60)
    print("  IaC GENERATOR")
    print("=" * 60)
    print(f"  Prompt : {prompt[:80]}{'...' if len(prompt) > 80 else ''}")
    print(f"  Output : {args.output}")
    print(f"  Model  : {os.environ.get('IAC_MODEL', 'claude-sonnet-4-6')}")
    print(f"  Validate: {'no' if args.no_validate else 'yes (terraform validate)'}")
    print("=" * 60)
    print()

    from src.graph.graph import iac_gen_graph
    from src.graph.state import initial_state

    state = initial_state(
        prompt=prompt,
        output_dir=args.output,
        max_retries=args.max_retries,
    )

    start = time.time()
    try:
        result = iac_gen_graph.invoke(state)
    except Exception as exc:
        log.error("Graph execution failed: %s", exc, exc_info=True)
        print(f"\n❌  Generation failed: {exc}")
        sys.exit(1)

    elapsed = time.time() - start

    # ── Print result ──────────────────────────────────────────────────────────
    print()
    print("=" * 60)
    print("  RESULT")
    print("=" * 60)

    status = result.get("final_status", "unknown")
    written = result.get("written_files", [])
    req = result.get("requirements", {})
    val_output = result.get("validation_output", "")

    if status == "success":
        print(f"  ✅  Terraform generated and validated ({elapsed:.1f}s)")
    elif status == "validation_failed":
        print(f"  ⚠️   Terraform generated but validation failed ({elapsed:.1f}s)")
        print(f"      Run `terraform validate` manually after reviewing the files.")
    elif status == "no_plan":
        print(f"  ❌  No resources planned — check your prompt and try again.")
    else:
        print(f"  ❓  Status: {status}")

    print()
    print(f"  Architecture : {req.get('compute', '?')} + {req.get('database', 'no db')} + {req.get('load_balancer', 'no lb')}")
    print(f"  Region       : {req.get('region', 'us-east-1')}")
    print(f"  App name     : {req.get('app_name', '?')}")
    print()

    if written:
        print("  Files written:")
        for f in written:
            size = Path(f).stat().st_size
            print(f"    📄 {Path(f).name}  ({size:,} bytes)")
        print()
        print("  Next steps:")
        print(f"    cd {args.output}")
        print("    terraform init")
        print("    terraform plan    # review what will be created")
        print("    terraform apply   # creates real AWS resources (costs money!)")
    else:
        print("  No files were written.")

    if val_output and status == "validation_failed":
        print()
        print("  Validation errors:")
        for line in val_output.splitlines()[:20]:
            print(f"    {line}")

    print("=" * 60)
    print()

    sys.exit(0 if status in ("success", "validation_failed") else 1)


if __name__ == "__main__":
    main()
