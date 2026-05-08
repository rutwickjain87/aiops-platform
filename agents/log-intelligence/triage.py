"""
triage.py — CLI entry point for the log triage agent. Three backends.

Usage:
    python triage.py <path-to-log-file> --backend anthropic
    python triage.py <path-to-log-file> --backend langchain
    python triage.py <path-to-log-file> --backend openrouter
    python triage.py --eval --backend anthropic
    python triage.py --help

Backends:
  --backend anthropic   Raw Anthropic SDK. Uses ANTHROPIC_API_KEY.
                        Files: planner_anthropic.py, tools_anthropic.py, memory_anthropic.py
                        Install: uv pip install -r requirements_anthropic.txt

  --backend langchain   LangChain bind_tools + explicit loop. Uses ANTHROPIC_API_KEY.
                        Files: planner_langchain.py
                        Install: uv pip install -r requirements_langchain.txt

  --backend openrouter  Anthropic Claude via OpenRouter (OpenAI-compatible API).
                        Uses OPENROUTER_API_KEY. Model swap = one string change.
                        Files: planner_openrouter.py, tools_openrouter.py, memory_openrouter.py
                        Install: uv pip install -r requirements_openrouter.txt

SETUP:
    cd ~/workspace/claude-code/ai-journey/agentic-ai-projects/aiops-platform/agents/log-intelligence
    uv venv && source .venv/bin/activate

    uv pip install -r requirements_anthropic.txt   # for --backend anthropic
    uv pip install -r requirements_langchain.txt   # for --backend langchain
    uv pip install -r requirements_openrouter.txt  # for --backend openrouter

ENV VARS:
    export ANTHROPIC_API_KEY="sk-ant-..."   # required for anthropic + langchain
    export OPENROUTER_API_KEY="sk-or-..."   # required for openrouter

RUN:
    LOG=~/workspace/claude-code/ai-journey/agentic-ai-projects/aiops-platform/services/ingestion/loghub-samples/HDFS/HDFS_2k.log

    python triage.py $LOG --backend anthropic
    python triage.py $LOG --backend langchain
    python triage.py $LOG --backend openrouter

    python triage.py --eval --backend anthropic
    python triage.py --eval --backend langchain
    python triage.py --eval --backend openrouter
"""

from __future__ import annotations
import argparse
import sys
import os
from pathlib import Path


# ── Agent factory — selects backend, returns .run(prompt) -> str ────────────


def make_agent(
    budget_usd: float = 1.00, backend: str = "anthropic", model: str | None = None
):
    """
    Returns an agent object with a .run(prompt: str) -> str interface.
    All three backends expose the same interface — triage.py doesn't need
    to know which one is active.

    Args:
        model: Override the model string for --backend openrouter only.
               E.g. "openai/gpt-4o-mini", "anthropic/claude-sonnet-4-6".
               Ignored for anthropic and langchain backends.
    """
    if backend == "langchain":
        from planner_langchain import LangChainPlanner, LangChainPlannerConfig

        return LangChainPlanner(config=LangChainPlannerConfig())

    elif backend == "openrouter":
        from planner_openrouter import OpenRouterPlanner, OpenRouterPlannerConfig
        from tools_openrouter import Tools
        from memory_openrouter import Memory
        from planner_openrouter import SYSTEM_PROMPT

        cfg = OpenRouterPlannerConfig()
        if model:
            cfg.model = model
        return OpenRouterPlanner(
            tools=Tools(),
            memory=Memory(system_prompt=SYSTEM_PROMPT),
            config=cfg,
        )

    else:  # anthropic (default)
        from planner_anthropic import Planner, PlannerConfig
        from tools_anthropic import Tools
        from memory_anthropic import Memory

        return Planner(
            tools=Tools(),
            memory=Memory(),
            config=PlannerConfig(budget_usd=budget_usd),
        )


# ── Triage prompt ─────────────────────────────────────────────────────────────

TRIAGE_PROMPT_TEMPLATE = """\
Triage the log file at: {log_path}

Instructions:
1. Use read_log_chunk to read the first 100 lines and get an initial picture.
2. Use grep to find all ERROR, WARN, and FATAL entries.
3. Use cluster_errors to group anomalies into time windows.
4. Based on what you find, produce a triage report with EXACTLY these sections:

## Severity
State the overall severity: P1 (critical/outage), P2 (degraded), P3 (warning/investigation needed), or P4 (informational).
Give a one-line justification.

## Root Cause Hypothesis
Your best hypothesis based on the log evidence. Cite specific log lines (timestamp + component + message).
If you see multiple hypotheses, list them ranked by likelihood.

## Suggested Actions
Numbered list of concrete next steps an on-call SRE should take, in priority order.
Be specific: name the component, tool, or metric to check.

Keep the report focused and factual. Do not pad.
"""


# ── CLI ────────────────────────────────────────────────────────────────────────

BACKEND_LABELS = {
    "anthropic": "Anthropic SDK",
    "langchain": "LangChain",
    "openrouter": "OpenRouter",
}

BACKEND_KEY_REQUIRED = {
    "anthropic": "ANTHROPIC_API_KEY",
    "langchain": "ANTHROPIC_API_KEY",
    "openrouter": "OPENROUTER_API_KEY",
}


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Log triage agent — reads a log file and produces a structured Markdown report.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "examples:\n"
            "  python triage.py /path/to/file.log --backend anthropic\n"
            "  python triage.py /path/to/file.log --backend langchain\n"
            "  python triage.py /path/to/file.log --backend openrouter\n"
            "  python triage.py --eval --backend anthropic\n"
        ),
    )
    parser.add_argument(
        "log_file",
        nargs="?",
        help="Absolute path to the log file to analyze.",
    )
    parser.add_argument(
        "--backend",
        choices=["anthropic", "langchain", "openrouter"],
        required=True,
        help=(
            "Backend to use: "
            "'anthropic' = raw Anthropic SDK; "
            "'langchain' = LangChain bind_tools; "
            "'openrouter' = Anthropic Claude via OpenRouter (OpenAI-compatible API)."
        ),
    )
    parser.add_argument(
        "--budget",
        type=float,
        default=1.00,
        help="Max $ to spend per run — Anthropic backend only (default: 1.00).",
    )
    parser.add_argument(
        "--eval",
        action="store_true",
        help="Run the eval suite instead of triaging a file.",
    )
    parser.add_argument(
        "--model",
        default=None,
        help=(
            "Override model string for --backend openrouter. "
            "E.g. 'openai/gpt-4o-mini', 'anthropic/claude-sonnet-4-6'. "
            "Ignored for anthropic and langchain backends."
        ),
    )
    args = parser.parse_args()

    # ── API key check ──────────────────────────────────────────────────────
    required_key = BACKEND_KEY_REQUIRED[args.backend]
    if not os.environ.get(required_key):
        print(
            f"ERROR: {required_key} not set. "
            f"Required for --backend {args.backend}. Add it to ~/.zshrc.",
            file=sys.stderr,
        )
        return 1

    # ── eval mode ──────────────────────────────────────────────────────────
    if args.eval:
        from evaluator import Evaluator

        results = Evaluator(
            lambda: make_agent(backend=args.backend, model=args.model)
        ).run()
        return 0 if all(r.passed for r in results) else 1

    # ── triage mode ────────────────────────────────────────────────────────
    if not args.log_file:
        parser.print_help()
        return 2

    log_path = Path(args.log_file).expanduser().resolve()
    if not log_path.exists():
        print(f"ERROR: file not found: {log_path}", file=sys.stderr)
        return 1

    prompt = TRIAGE_PROMPT_TEMPLATE.format(log_path=str(log_path))
    label = BACKEND_LABELS[args.backend]

    print(f"# Triage Report: {log_path.name}  [{label}]\n")
    agent = make_agent(budget_usd=args.budget, backend=args.backend, model=args.model)
    print(agent.run(prompt))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
