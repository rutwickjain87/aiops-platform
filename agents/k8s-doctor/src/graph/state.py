"""
src/graph/state.py — LangGraph state shape for the K8s Doctor agent.

DESIGN PRINCIPLE
────────────────
Design the state shape before writing any node code.
State is the contract between nodes — get it wrong and you refactor everything.

STATE LIFECYCLE
───────────────
  Initial input (from CLI):
    symptom   → "CrashLoopBackOff"
    namespace → "doctor-lab"
    resource  → "crashloop-demo"

  observe node fills:
    observations[]  → raw kubectl/prom output strings
    model_used      → "claude-haiku-4-5-20251001"  (cheap reads)

  hypothesize node fills:
    hypotheses[]    → ranked list of root cause hypotheses
    model_used      → "claude-sonnet-4-6"  (reasoning)

  propose node fills:
    final_diagnosis → structured markdown: root cause + remediation steps
    model_used      → "claude-sonnet-4-6"  (high-stakes output)

NOTE: model_used is updated by each node so LangSmith traces and Day 7
model-routing experiments can see which model handled which step.
"""

from __future__ import annotations

from typing import Annotated

from langgraph.graph.message import add_messages
from typing_extensions import TypedDict


class K8sDoctorState(TypedDict):
    # ── Input (set by CLI, never mutated by nodes) ────────────────────────────
    symptom: str          # e.g. "CrashLoopBackOff", "ImagePullBackOff", "OOMKilled"
    namespace: str        # k8s namespace, e.g. "doctor-lab"
    resource: str         # deployment/pod name, e.g. "crashloop-demo"

    # ── Accumulated by observe node ───────────────────────────────────────────
    observations: list[str]   # raw tool outputs: kubectl describe, logs, events

    # ── Accumulated by hypothesize node ──────────────────────────────────────
    hypotheses: list[str]     # ranked root cause hypotheses

    # ── Control flow ─────────────────────────────────────────────────────────
    next_action: str          # what the agent wants to do next (for conditional edges)

    # ── Observability (updated by each node — used for Day 7 routing) ────────
    model_used: str           # model slug that ran the last node

    # ── Output (filled by propose node) ──────────────────────────────────────
    final_diagnosis: str | None   # markdown: root cause + remediation steps

    # ── LangGraph message history (for multi-turn nodes if needed) ───────────
    messages: Annotated[list, add_messages]


def initial_state(symptom: str, namespace: str, resource: str) -> K8sDoctorState:
    """Build the starting state from CLI inputs."""
    return K8sDoctorState(
        symptom=symptom,
        namespace=namespace,
        resource=resource,
        observations=[],
        hypotheses=[],
        next_action="observe",
        model_used="",
        final_diagnosis=None,
        messages=[],
    )
