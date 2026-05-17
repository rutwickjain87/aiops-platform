"""
src/graph/graph.py — LangGraph StateGraph wiring for the K8s Doctor.

GRAPH STRUCTURE
───────────────
  START
    │
    ▼
  observe          (kubectl describe / logs / events + Prometheus)
    │
    ▼
  hypothesize      (rank root cause hypotheses)
    │
    ▼
  propose          (final diagnosis + remediation playbook)
    │
    ▼
  END

This is a linear graph for Day 6. Day 7 adds conditional branching
(e.g. loop back to observe if confidence is LOW) and model routing.

LANGGRAPH CONCEPTS DEMONSTRATED
────────────────────────────────
  StateGraph:   Graph where nodes read/write a shared typed state dict
  add_node:     Register a Python function as a graph node
  add_edge:     Fixed transition between nodes
  compile():    Returns a runnable graph (Pregel executor under the hood)
  invoke():     Run the graph synchronously with an initial state
"""

from __future__ import annotations

from langgraph.graph import END, START, StateGraph

from src.graph.nodes import hypothesize, observe, propose
from src.graph.state import K8sDoctorState


def build_graph():
    """Build and compile the K8s Doctor LangGraph."""
    graph = StateGraph(K8sDoctorState)

    # ── Register nodes ────────────────────────────────────────────────────────
    graph.add_node("observe", observe)
    graph.add_node("hypothesize", hypothesize)
    graph.add_node("propose", propose)

    # ── Wire edges (linear for Day 6) ─────────────────────────────────────────
    graph.add_edge(START, "observe")
    graph.add_edge("observe", "hypothesize")
    graph.add_edge("hypothesize", "propose")
    graph.add_edge("propose", END)

    return graph.compile()


# Module-level compiled graph — import this in doctor.py
k8s_doctor_graph = build_graph()
