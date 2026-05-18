"""
Alert Correlator LangGraph pipeline.

Graph:  ingest → embed → query_similar → cluster → emit_incident

Linear pipeline — no conditional edges needed here because every node
always has valid output to pass forward (errors are accumulated, not fatal).
"""
from langgraph.graph import StateGraph, END

from .state import AlertCorrelatorState
from .nodes import ingest, embed, query_similar, cluster, emit_incident


def build_graph() -> StateGraph:
    g = StateGraph(AlertCorrelatorState)

    g.add_node("ingest", ingest)
    g.add_node("embed", embed)
    g.add_node("query_similar", query_similar)
    g.add_node("cluster", cluster)
    g.add_node("emit_incident", emit_incident)

    g.set_entry_point("ingest")
    g.add_edge("ingest", "embed")
    g.add_edge("embed", "query_similar")
    g.add_edge("query_similar", "cluster")
    g.add_edge("cluster", "emit_incident")
    g.add_edge("emit_incident", END)

    return g.compile()


# Singleton — build once at import time
graph = build_graph()
