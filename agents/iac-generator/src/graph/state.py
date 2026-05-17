"""
src/graph/state.py — LangGraph state shape for the IaC Generator.

STATE LIFECYCLE
───────────────
  CLI input:
    prompt       → natural-language infrastructure description
    output_dir   → where to write the generated .tf files
    max_retries  → max terraform validate retry attempts (default: 2)

  clarify node:
    requirements → structured dict extracted from the prompt
                   (provider, region, compute, database, networking, app_name, …)

  plan node:
    resource_plan → ordered list of AWS resource dicts with types + descriptions

  generate node:
    generated_files → dict mapping filename → HCL content
                      e.g. {"main.tf": "...", "variables.tf": "...", ...}
    validation_errors → populated on retry with terraform error output

  validate node:
    validation_output → raw terraform validate stdout/stderr
    validation_passed → True if exit code 0

  output node:
    written_files → list of absolute paths written to disk
    final_status  → "success" | "validation_failed" | "no_plan"
"""

from __future__ import annotations

from typing import Annotated

from langgraph.graph.message import add_messages
from typing_extensions import TypedDict


class IacGenState(TypedDict):
    # ── Input ─────────────────────────────────────────────────────────────────
    prompt: str                    # raw user description
    output_dir: str                # where to write .tf files
    max_retries: int               # max validate retries (default: 2)

    # ── clarify node ──────────────────────────────────────────────────────────
    requirements: dict             # structured requirements extracted from prompt

    # ── plan node ─────────────────────────────────────────────────────────────
    resource_plan: list[dict]      # ordered list of resource dicts
                                   # e.g. [{"type": "aws_vpc", "name": "main",
                                   #         "description": "..."}]

    # ── generate node ─────────────────────────────────────────────────────────
    generated_files: dict[str, str]  # filename → HCL content
    validation_errors: str           # terraform errors fed back on retry

    # ── validate node ─────────────────────────────────────────────────────────
    validation_output: str         # raw terraform validate output
    validation_passed: bool        # True if terraform validate exits 0

    # ── retry tracking ────────────────────────────────────────────────────────
    retry_count: int               # fix retries so far

    # ── output node ───────────────────────────────────────────────────────────
    written_files: list[str]       # absolute paths of written .tf files
    final_status: str              # "success" | "validation_failed" | "no_plan"

    # ── LangGraph message history ──────────────────────────────────────────────
    messages: Annotated[list, add_messages]


def initial_state(
    prompt: str,
    output_dir: str,
    max_retries: int = 2,
) -> IacGenState:
    """Build the initial state from CLI inputs."""
    return IacGenState(
        prompt=prompt,
        output_dir=output_dir,
        max_retries=max_retries,
        requirements={},
        resource_plan=[],
        generated_files={},
        validation_errors="",
        validation_output="",
        validation_passed=False,
        retry_count=0,
        written_files=[],
        final_status="",
        messages=[],
    )
