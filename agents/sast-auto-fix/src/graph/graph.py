"""
src/graph/graph.py — LangGraph StateGraph wiring for the SAST Auto-Fixer.

GRAPH STRUCTURE
───────────────
                    ┌─────────────────────────────┐
  START → scan → pick → read_ctx → fix → validate ┤
                                         ↑  pass   └→ open_pr → END
                                         │  fail+retry↑
                                         └────────────┘
                                            fail+no retries → end_failed → END

CONDITIONAL EDGE (route_after_validate)
───────────────────────────────────────
  "open_pr"    — tests passed
  "fix"        — tests failed, retries remaining
  "end_failed" — tests failed, max retries exhausted

NOTE: pick → END shortcut when no findings are present
(final_status = "no_findings" is set in the pick node)
"""

from __future__ import annotations

from langgraph.graph import END, START, StateGraph

from src.graph.nodes import (
    end_failed,
    fix,
    open_pr,
    pick,
    read_ctx,
    route_after_validate,
    scan,
    validate,
)
from src.graph.state import SastFixState


def _route_after_pick(state: SastFixState) -> str:
    """Skip the rest of the graph if there are no findings."""
    if state.get("final_status") == "no_findings":
        return END
    return "read_ctx"


def build_graph():
    """Build and compile the SAST Auto-Fixer LangGraph."""
    graph = StateGraph(SastFixState)

    # ── Register nodes ────────────────────────────────────────────────────────
    graph.add_node("scan",       scan)
    graph.add_node("pick",       pick)
    graph.add_node("read_ctx",   read_ctx)
    graph.add_node("fix",        fix)
    graph.add_node("validate",   validate)
    graph.add_node("open_pr",    open_pr)
    graph.add_node("end_failed", end_failed)

    # ── Fixed edges ───────────────────────────────────────────────────────────
    graph.add_edge(START,      "scan")
    graph.add_edge("scan",     "pick")
    graph.add_edge("read_ctx", "fix")
    graph.add_edge("fix",      "validate")
    graph.add_edge("open_pr",  END)
    graph.add_edge("end_failed", END)

    # ── Conditional: pick → read_ctx (findings exist) or END (no findings) ───
    graph.add_conditional_edges(
        "pick",
        _route_after_pick,
        {"read_ctx": "read_ctx", END: END},
    )

    # ── Conditional: validate → open_pr | fix (retry) | end_failed ───────────
    graph.add_conditional_edges(
        "validate",
        route_after_validate,
        {
            "open_pr":    "open_pr",
            "fix":        "fix",
            "end_failed": "end_failed",
        },
    )

    return graph.compile()


# Module-level compiled graph
sast_fix_graph = build_graph()
