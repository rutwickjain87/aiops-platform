"""
The 4 CrewAI agents of the Incident Commander.

Agent roster:
  1. Triage Agent      — classifies severity + affected scope (Sonnet)
  2. Investigator      — digs into root cause with kubectl + Prometheus (Sonnet)
  3. Mitigator         — proposes and (with approval) applies remediations (Sonnet)
  4. Communicator      — writes the Slack incident card (Haiku — cheap, good at formatting)

Triage + Investigator run in parallel (CrewAI sequential_tasks=False on their task group).
Mitigator waits for both. Communicator waits for Mitigator.
"""
from crewai import Agent
from langchain_anthropic import ChatAnthropic

from ..tools.kubectl_tool import (
    get_pod_logs, describe_pod, get_pods_in_namespace,
    get_events, get_node_status, get_deployment_status,
    restart_deployment, scale_deployment, patch_resource_limits,
)
from ..tools.prometheus_tool import (
    query_error_rate, query_memory_usage, query_cpu_usage,
    query_pod_restarts, query_node_disk_usage,
)
from ..tools.slack_tool import post_incident_card, post_resolution_update

# ---------------------------------------------------------------------------
# LLM instances — model routing:
# Sonnet for reasoning-heavy agents, Haiku for the Communicator
# ---------------------------------------------------------------------------
_sonnet = ChatAnthropic(model="claude-sonnet-4-6", temperature=0, max_tokens=2048)
_haiku = ChatAnthropic(model="claude-haiku-4-5-20251001", temperature=0, max_tokens=1024)


# ---------------------------------------------------------------------------
# Agent 1: Triage Agent
# ---------------------------------------------------------------------------
triage_agent = Agent(
    role="Incident Triage Specialist",
    goal=(
        "Given a raw incident description, classify its severity (critical/warning/info), "
        "identify the blast radius (which namespaces, services, or nodes are affected), "
        "and determine whether the incident is a cascade (multiple related alerts) "
        "or an isolated anomaly."
    ),
    backstory=(
        "You are a senior SRE who has seen thousands of production incidents. "
        "You are fast, systematic, and you never panic. Your job is to produce a "
        "structured triage report in the first 90 seconds of an incident — before "
        "the Investigator starts digging. You do NOT attempt remediations. "
        "Your output is always a concise structured summary."
    ),
    tools=[get_pods_in_namespace, get_events, get_node_status],
    llm=_sonnet,
    verbose=True,
    allow_delegation=False,
    max_iter=5,
)


# ---------------------------------------------------------------------------
# Agent 2: Investigator
# ---------------------------------------------------------------------------
investigator_agent = Agent(
    role="Root Cause Investigator",
    goal=(
        "Given the incident context, investigate root cause by examining pod logs, "
        "Kubernetes events, and Prometheus metrics. Produce a root cause hypothesis "
        "with supporting evidence (log snippets, metric values). "
        "Assign a confidence level: High / Medium / Low."
    ),
    backstory=(
        "You are a staff engineer who specialises in distributed systems debugging. "
        "You follow a systematic playbook: check logs → check events → check metrics → "
        "form hypothesis → validate with data. You never guess without evidence. "
        "You are comfortable reading Prometheus output and kubectl describe output."
    ),
    tools=[
        get_pod_logs, describe_pod, get_events,
        query_error_rate, query_memory_usage, query_cpu_usage,
        query_pod_restarts, query_node_disk_usage,
    ],
    llm=_sonnet,
    verbose=True,
    allow_delegation=False,
    max_iter=8,
)


# ---------------------------------------------------------------------------
# Agent 3: Mitigator
# ---------------------------------------------------------------------------
mitigator_agent = Agent(
    role="Incident Mitigator",
    goal=(
        "Given the triage report and root cause investigation, propose the most "
        "appropriate remediation steps. If REQUIRE_HUMAN_APPROVAL is true (the default), "
        "present the plan and wait for human approval before executing any kubectl mutations. "
        "After executing, verify the fix took effect by re-checking pod status."
    ),
    backstory=(
        "You are a principal engineer with change management training. You never apply "
        "a fix without understanding its blast radius. You always propose before acting, "
        "you always verify after acting, and you document what you did. "
        "Your motto: 'Measure twice, kubectl once.'"
    ),
    tools=[
        get_pod_logs, describe_pod, get_deployment_status,
        restart_deployment, scale_deployment, patch_resource_limits,
        query_error_rate, query_memory_usage,
    ],
    llm=_sonnet,
    verbose=True,
    allow_delegation=False,
    max_iter=6,
)


# ---------------------------------------------------------------------------
# Agent 4: Communicator
# ---------------------------------------------------------------------------
communicator_agent = Agent(
    role="Incident Communicator",
    goal=(
        "Write and post a clear, actionable incident card to Slack. The card must include: "
        "incident ID, severity, affected services, 2-sentence summary, "
        "3 recommended next actions, and current status. "
        "Also post a resolution update once the Mitigator reports success."
    ),
    backstory=(
        "You are a technical writer embedded in the SRE team. You translate dense "
        "engineering incident reports into clear, scannable Slack messages that on-call "
        "engineers and managers can act on immediately. You are concise, never alarmist, "
        "and always include a clear status and next step."
    ),
    tools=[post_incident_card, post_resolution_update],
    llm=_haiku,  # Haiku is fast and cheap — perfect for formatting tasks
    verbose=True,
    allow_delegation=False,
    max_iter=3,
)
