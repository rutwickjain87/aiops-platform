"""
doctor.py — CLI entry point for the K8s Doctor LangGraph agent.

USAGE
─────
# Diagnose a CrashLoopBackOff (dry-run, no cluster changes)
python doctor.py --namespace doctor-lab --resource crashloop-demo

# Diagnose an ImagePullBackOff
python doctor.py --namespace doctor-lab --resource imagepull-demo --symptom ImagePullBackOff

# Diagnose an OOMKilled workload
python doctor.py --namespace doctor-lab --resource oom-demo --symptom OOMKilled

# Apply remediation steps with human approval gate (Day 7)
python doctor.py --namespace doctor-lab --resource crashloop-demo --apply

# Use a specific kind context
python doctor.py --namespace doctor-lab --resource crashloop-demo --context kind-doctor-lab

# Enable LangSmith tracing
LANGSMITH_TRACING=true python doctor.py --namespace doctor-lab --resource crashloop-demo

ENVIRONMENT VARIABLES
─────────────────────
  ANTHROPIC_API_KEY    Required. Powers the LLM nodes.
  K8S_CONTEXT          kubectl context (default: kind-doctor-lab)
  OBSERVE_MODEL        Model for observe node (default: claude-haiku-4-5-20251001)
  REASON_MODEL         Model for hypothesize/propose nodes (default: claude-sonnet-4-6)
  PROMETHEUS_URL       Prometheus base URL (default: http://localhost:9090)
  LANGSMITH_TRACING    Set to "true" to send traces to LangSmith
  LANGSMITH_PROJECT    LangSmith project name (default: k8s-doctor)
"""

from __future__ import annotations

import argparse
import logging
import os
import re
import sys
import time
from pathlib import Path

from dotenv import load_dotenv

# Load .env from agent directory before any env var reads
load_dotenv(Path(__file__).parent / ".env")

# Set up basic logging — structured logs come from the nodes themselves
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
log = logging.getLogger("doctor")


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="K8s Doctor — LangGraph-powered Kubernetes failure diagnosis",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    p.add_argument(
        "--namespace", "-n",
        default="doctor-lab",
        help="Kubernetes namespace to inspect (default: doctor-lab)",
    )
    p.add_argument(
        "--resource", "-r",
        required=True,
        help="Deployment or pod name to diagnose (e.g. crashloop-demo)",
    )
    p.add_argument(
        "--symptom", "-s",
        default="CrashLoopBackOff",
        help="Failure symptom hint (default: CrashLoopBackOff)",
    )
    p.add_argument(
        "--context",
        default=os.environ.get("K8S_CONTEXT", "kind-doctor-lab"),
        help="kubectl context (default: kind-doctor-lab)",
    )
    p.add_argument(
        "--observe-model",
        default=None,
        help="Override OBSERVE_MODEL env var (observe node model)",
    )
    p.add_argument(
        "--reason-model",
        default=None,
        help="Override REASON_MODEL env var (hypothesize + propose model)",
    )
    p.add_argument(
        "--apply",
        action="store_true",
        default=False,
        help=(
            "After diagnosis, present each remediation step and ask for "
            "explicit y/n approval before printing it as a command to run. "
            "Requires an interactive terminal. Refused in CI (no TTY)."
        ),
    )
    return p.parse_args()


# ── Human approval gate ────────────────────────────────────────────────────────

def _is_interactive() -> bool:
    """Return True only when stdin and stdout are a real TTY (not piped or CI)."""
    return sys.stdin.isatty() and sys.stdout.isatty()


def _extract_remediation_steps(diagnosis: str) -> list[str]:
    """
    Parse numbered remediation steps from the ## Remediation Steps section.

    Looks for lines like "1. kubectl ..." or "2. ..." inside the section.
    Returns a list of step strings (stripped), empty list if section not found.
    """
    section_match = re.search(
        r"##\s+Remediation Steps\s*\n(.*?)(?=\n##|\Z)",
        diagnosis,
        re.DOTALL | re.IGNORECASE,
    )
    if not section_match:
        return []

    section = section_match.group(1)
    steps = []
    for line in section.splitlines():
        m = re.match(r"^\s*(\d+)\.\s+(.+)", line)
        if m:
            steps.append(m.group(2).strip())
    return steps


def run_apply_gate(diagnosis: str, resource: str, namespace: str) -> None:
    """
    Present each remediation step to the user and ask for explicit approval.

    Safety contract:
      - Refuses to run in non-interactive contexts (CI, pipes).
      - Does NOT execute commands — only prints approved steps.
      - Default answer is NO. Requires explicit 'y' or 'yes'.
      - Stops on the first rejection (user can re-run for remaining steps).

    Args:
        diagnosis:  The final_diagnosis string from the propose node.
        resource:   Resource name (for display only).
        namespace:  Namespace (for display only).
    """
    if not _is_interactive():
        print(
            "\n⚠️  --apply requested but no interactive TTY detected.\n"
            "   Running in non-interactive mode (CI/pipe) — skipping apply gate.\n"
            "   Re-run in a terminal to step through remediation interactively.",
            file=sys.stderr,
        )
        return

    steps = _extract_remediation_steps(diagnosis)

    if not steps:
        print(
            "\n⚠️  --apply: could not parse remediation steps from the diagnosis.\n"
            "   Review the ## Remediation Steps section manually.",
            file=sys.stderr,
        )
        return

    print(f"\n{'─' * 60}")
    print(f"  APPLY MODE — {namespace}/{resource}")
    print(f"  {len(steps)} remediation step(s) found.")
    print(f"  Each step requires explicit approval. Default: NO.")
    print(f"{'─' * 60}\n")

    approved = 0
    for i, step in enumerate(steps, 1):
        print(f"  Step {i}/{len(steps)}:")
        print(f"  ❯ {step}\n")
        try:
            answer = input("  Apply this step? [y/N] ").strip().lower()
        except (EOFError, KeyboardInterrupt):
            print("\n  [Aborted]")
            break

        if answer in ("y", "yes"):
            print(f"  ✅ Approved — run: {step}")
            approved += 1
        else:
            print("  ❌ Skipped.")

        print()

    print(f"{'─' * 60}")
    print(f"  Apply summary: {approved}/{len(steps)} step(s) approved.")
    print(
        "  ⚠️  K8s Doctor does NOT execute commands automatically.\n"
        "      Copy approved steps above and run them in your terminal."
    )
    print(f"{'─' * 60}\n")


# ── Main ───────────────────────────────────────────────────────────────────────

def main() -> None:
    args = parse_args()

    # Apply model overrides from CLI flags
    if args.observe_model:
        os.environ["OBSERVE_MODEL"] = args.observe_model
    if args.reason_model:
        os.environ["REASON_MODEL"] = args.reason_model
    if args.context:
        os.environ["K8S_CONTEXT"] = args.context

    # Import after env is configured so model constants pick up overrides
    from src.graph.graph import k8s_doctor_graph
    from src.graph.state import initial_state

    observe_model = os.environ.get("OBSERVE_MODEL", "claude-haiku-4-5-20251001")
    reason_model = os.environ.get("REASON_MODEL", "claude-sonnet-4-6")

    print(f"\n{'=' * 60}")
    print(f"  K8s Doctor — {args.namespace}/{args.resource}")
    print(f"  Symptom      : {args.symptom}")
    print(f"  Context      : {args.context}")
    print(f"  Observe model: {observe_model}")
    print(f"  Reason model : {reason_model}")
    print(f"  Apply gate   : {'ON' if args.apply else 'off'}")
    print(f"  Tracing      : {os.environ.get('LANGSMITH_TRACING', 'false')}")
    print(f"{'=' * 60}\n")

    state = initial_state(
        symptom=args.symptom,
        namespace=args.namespace,
        resource=args.resource,
    )

    start = time.time()
    try:
        print("▶ Running graph: observe → hypothesize → propose\n")
        result = k8s_doctor_graph.invoke(state)
    except KeyboardInterrupt:
        print("\n[Interrupted]")
        sys.exit(0)
    except Exception as exc:
        log.exception("Graph execution failed: %s", exc)
        sys.exit(1)

    elapsed = time.time() - start
    diagnosis = result.get("final_diagnosis", "[No diagnosis produced]")

    print(f"\n{'=' * 60}")
    print("  DIAGNOSIS")
    print(f"{'=' * 60}\n")
    print(diagnosis)
    print(f"\n{'=' * 60}")
    print(f"  Completed in {elapsed:.1f}s  |  Last model: {result.get('model_used', '?')}")
    print(f"{'=' * 60}\n")

    # ── Day 7: human approval gate ─────────────────────────────────────────────
    if args.apply:
        run_apply_gate(diagnosis, resource=args.resource, namespace=args.namespace)


if __name__ == "__main__":
    main()
