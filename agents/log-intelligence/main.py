"""
main.py — entry point.

Wires planner + tools + memory together. Single CLI entry point. Keep this
small; if it grows beyond ~80 lines you're putting business logic in the
wrong place.
"""
from __future__ import annotations
import argparse
import sys

from planner import Planner, PlannerConfig
from tools import Tools
from memory import Memory


def make_agent(budget_usd: float = 1.00) -> Planner:
    return Planner(
        tools=Tools(),
        memory=Memory(),
        config=PlannerConfig(budget_usd=budget_usd),
    )


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("input", nargs="?", help="Prompt for the agent")
    p.add_argument("--budget", type=float, default=1.00, help="Max $ per run")
    p.add_argument("--eval", action="store_true", help="Run eval suite instead")
    args = p.parse_args()

    if args.eval:
        from evaluator import Evaluator
        results = Evaluator(make_agent).run()
        return 0 if all(r.passed for r in results) else 1

    if not args.input:
        print("usage: main.py <prompt>  |  main.py --eval", file=sys.stderr)
        return 2

    agent = make_agent(budget_usd=args.budget)
    print(agent.run(args.input))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
