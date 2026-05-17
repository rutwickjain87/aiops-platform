"""
src/graph/graph.py — LangGraph StateGraph wiring for the IaC Generator.

GRAPH TOPOLOGY
──────────────
  START → clarify → plan → generate → validate ─(pass)→ output → END
                                          ↑                 │
                                          └──(fail, retry < max)──┘
                                                   │
                                          (fail, retry >= max)
                                                   ↓
                                               output → END   ← writes files anyway
                                                              with final_status="validation_failed"

The retry edge sends control back to `generate` (not `plan`) because the plan
is correct — only the HCL content needs fixing based on the validation errors.
"""

from __future__ import annotations

from langgraph.graph import END, START, StateGraph

from src.graph.nodes import clarify, generate, output, plan, validate
from src.graph.state import IacGenState


def _route_after_validate(state: IacGenState) -> str:
    """
    Conditional edge after the validate node.
      - Passed           → output
      - Failed, retries left → generate  (LLM fixes errors)
      - Failed, no retries   → output    (write anyway, status=validation_failed)
    """
    if state["validation_passed"]:
        return "output"
    if state["retry_count"] < state["max_retries"]:
        return "generate"
    return "output"


def build_graph() -> StateGraph:
    g = StateGraph(IacGenState)

    # Nodes
    g.add_node("clarify", clarify)
    g.add_node("plan", plan)
    g.add_node("generate", generate)
    g.add_node("validate", validate)
    g.add_node("output", output)

    # Edges
    g.add_edge(START, "clarify")
    g.add_edge("clarify", "plan")
    g.add_edge("plan", "generate")
    g.add_edge("generate", "validate")
    g.add_conditional_edges("validate", _route_after_validate, {
        "generate": "generate",
        "output": "output",
    })
    g.add_edge("output", END)

    return g.compile()


iac_gen_graph = build_graph()
