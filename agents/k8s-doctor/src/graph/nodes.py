"""
src/graph/nodes.py — LangGraph node implementations for the K8s Doctor.

GRAPH FLOW
──────────
  observe → hypothesize → propose → END

  observe:     Gathers raw facts using kubectl and Prometheus tools.
               Model: claude-haiku (cheap, deterministic reads)

  hypothesize: Reasons over observations to rank root cause hypotheses.
               Model: claude-sonnet (complex reasoning)

  propose:     Produces the final diagnosis and remediation playbook.
               Model: claude-sonnet (high-stakes, clear output required)

Each node returns a partial state dict — LangGraph merges it into the
running state automatically.

MODEL ROUTING (Day 7 preview)
──────────────────────────────
OBSERVE_MODEL and REASON_MODEL are read from env vars so Day 7 can
swap them without touching this file. The state["model_used"] field
records which model ran each node for cost/quality comparison.
"""

from __future__ import annotations

import logging
import os

from langchain_anthropic import ChatAnthropic
from langchain_core.messages import HumanMessage, SystemMessage

from src.graph.state import K8sDoctorState
from src.tools.kubectl import (
    kubectl_describe,
    kubectl_events,
    kubectl_get_pods,
    kubectl_logs,
)
from src.tools.prometheus import prom_query

log = logging.getLogger(__name__)

# ── Model routing — override via env for Day 7 experiments ───────────────────
OBSERVE_MODEL = os.environ.get("OBSERVE_MODEL", "claude-haiku-4-5-20251001")
REASON_MODEL = os.environ.get("REASON_MODEL", "claude-sonnet-4-6")


# ── Node: observe ─────────────────────────────────────────────────────────────

def observe(state: K8sDoctorState) -> dict:
    """
    Gather raw facts about the failing resource using kubectl and Prometheus.

    Runs four read-only kubectl commands and one Prometheus query, then asks
    the LLM to summarise the key signals into a concise observations list.
    """
    ns = state["namespace"]
    res = state["resource"]
    ctx = os.environ.get("K8S_CONTEXT", "kind-doctor-lab")

    log.info("observe: gathering facts for %s/%s", ns, res)

    # ── Collect raw tool outputs ──────────────────────────────────────────────
    raw = {
        "pods":     kubectl_get_pods(ns, context=ctx),
        "describe": kubectl_describe(res, ns, context=ctx),
        "logs":     kubectl_logs(res, ns, context=ctx),
        "prev_logs": kubectl_logs(res, ns, previous=True, context=ctx),
        "events":   kubectl_events(ns, context=ctx),
        "prom_up":  prom_query(f'kube_pod_status_phase{{namespace="{ns}"}}'),
    }

    tool_dump = "\n\n".join(
        f"=== {k.upper()} ===\n{v}" for k, v in raw.items()
    )

    # ── Ask LLM to extract key signals ───────────────────────────────────────
    llm = ChatAnthropic(model=OBSERVE_MODEL, max_tokens=1024)
    messages = [
        SystemMessage(content=(
            "You are a Kubernetes SRE. Extract the key diagnostic signals from "
            "the raw kubectl and Prometheus output below. Be concise — list only "
            "the facts that are relevant to diagnosing the failure. "
            "Return a numbered list of observations, one per line."
        )),
        HumanMessage(content=(
            f"Symptom: {state['symptom']}\n"
            f"Resource: {res} in namespace {ns}\n\n"
            f"{tool_dump}"
        )),
    ]

    response = llm.invoke(messages)
    observation_text = response.content.strip()

    log.info("observe: extracted %d chars of observations", len(observation_text))

    return {
        "observations": [observation_text],
        "model_used": OBSERVE_MODEL,
        "next_action": "hypothesize",
    }


# ── Node: hypothesize ─────────────────────────────────────────────────────────

def hypothesize(state: K8sDoctorState) -> dict:
    """
    Reason over the observations to generate ranked root cause hypotheses.

    Takes all collected observations and asks the LLM to produce a ranked
    list of hypotheses from most to least likely, with brief evidence for each.
    """
    log.info("hypothesize: reasoning over %d observation blocks", len(state["observations"]))

    observations_text = "\n\n".join(state["observations"])

    llm = ChatAnthropic(model=REASON_MODEL, max_tokens=2048)
    messages = [
        SystemMessage(content=(
            "You are a senior Kubernetes SRE. Given the observations below, "
            "generate a ranked list of root cause hypotheses. "
            "For each hypothesis:\n"
            "1. State the hypothesis clearly\n"
            "2. Cite the specific evidence from the observations\n"
            "3. Rate your confidence: HIGH / MEDIUM / LOW\n\n"
            "Order from most likely to least likely."
        )),
        HumanMessage(content=(
            f"Symptom: {state['symptom']}\n"
            f"Resource: {state['resource']} in namespace {state['namespace']}\n\n"
            f"OBSERVATIONS:\n{observations_text}"
        )),
    ]

    response = llm.invoke(messages)
    hypothesis_text = response.content.strip()

    log.info("hypothesize: generated hypotheses (%d chars)", len(hypothesis_text))

    return {
        "hypotheses": [hypothesis_text],
        "model_used": REASON_MODEL,
        "next_action": "propose",
    }


# ── Node: propose ─────────────────────────────────────────────────────────────

def propose(state: K8sDoctorState) -> dict:
    """
    Produce the final diagnosis and a step-by-step remediation playbook.

    Synthesises observations + hypotheses into a structured Markdown report
    suitable for posting to Slack or a runbook.
    """
    log.info("propose: producing final diagnosis")

    observations_text = "\n\n".join(state["observations"])
    hypotheses_text = "\n\n".join(state["hypotheses"])

    llm = ChatAnthropic(model=REASON_MODEL, max_tokens=2048)
    messages = [
        SystemMessage(content=(
            "You are a senior Kubernetes SRE writing an incident diagnosis. "
            "Produce a structured Markdown report with these sections:\n\n"
            "## Root Cause\n"
            "One clear sentence stating the most likely root cause.\n\n"
            "## Evidence\n"
            "Bullet list of the 3-5 most important observations supporting this diagnosis.\n\n"
            "## Remediation Steps\n"
            "Numbered list of specific kubectl or config changes to fix the issue. "
            "Include the exact command where possible.\n\n"
            "## Verification\n"
            "How to confirm the fix worked (what to check, what to look for).\n\n"
            "Be specific. Do not hedge unnecessarily. Prefer short sentences."
        )),
        HumanMessage(content=(
            f"Symptom: {state['symptom']}\n"
            f"Resource: {state['resource']} in namespace {state['namespace']}\n\n"
            f"OBSERVATIONS:\n{observations_text}\n\n"
            f"HYPOTHESES:\n{hypotheses_text}"
        )),
    ]

    response = llm.invoke(messages)
    diagnosis = response.content.strip()

    log.info("propose: diagnosis complete (%d chars)", len(diagnosis))

    return {
        "final_diagnosis": diagnosis,
        "model_used": REASON_MODEL,
        "next_action": "done",
    }


# ── Routing function ──────────────────────────────────────────────────────────

def route(state: K8sDoctorState) -> str:
    """Conditional edge function — returns the next node name from state."""
    return state.get("next_action", "propose")
