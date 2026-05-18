"""
CrewAI task definitions for the Incident Commander.

Execution order:
  Phase 1 (parallel): triage_task + investigate_task
  Phase 2 (sequential): mitigate_task
  Phase 3 (sequential): communicate_task
"""
from crewai import Task

from ..agents.agents import (
    triage_agent, investigator_agent, mitigator_agent, communicator_agent
)


def build_tasks(incident: dict) -> list[Task]:
    """
    Build the 4 CrewAI tasks for a given incident dict.
    incident must have: incident_id, severity, title, summary, alert_count,
    representative_alert (with labels.namespace, labels.alertname, etc.)
    """
    rep = incident.get("representative_alert", {})
    labels = rep.get("labels", {})
    annotations = rep.get("annotations", {})
    namespace = labels.get("namespace", "default")
    alertname = labels.get("alertname", "UnknownAlert")
    severity = incident.get("severity", "warning")
    incident_id = incident.get("incident_id", "INC-UNKNOWN")
    title = incident.get("title", "Untitled Incident")
    summary = incident.get("summary", annotations.get("summary", ""))
    alert_count = incident.get("alert_count", 1)

    # ------------------------------------------------------------------
    # Task 1: Triage (runs in parallel with Investigate)
    # ------------------------------------------------------------------
    triage_task = Task(
        description=f"""
Triage this incident immediately:

Incident ID: {incident_id}
Severity: {severity}
Title: {title}
Alert count: {alert_count}
Primary namespace: {namespace}
Primary alert: {alertname}
Summary: {summary}

Steps:
1. Use get_pods_in_namespace to check pod health in namespace '{namespace}'
2. Use get_events to fetch recent events in '{namespace}'
3. Classify: is this a cascade (multiple linked alerts) or isolated anomaly?
4. Identify the blast radius: which services, pods, or nodes are affected?

Produce a structured triage report:
- Severity classification (CRITICAL / WARNING / INFO)
- Blast radius: affected namespace(s), services, pods
- Incident type: cascade | isolated | unknown
- Key observations (2-3 bullet points)
- Urgency: immediate action required? yes/no
        """,
        expected_output=(
            "A structured triage report with: severity, blast radius (affected namespaces/services/pods), "
            "incident type (cascade/isolated), 2-3 key observations, urgency flag."
        ),
        agent=triage_agent,
    )

    # ------------------------------------------------------------------
    # Task 2: Investigate (runs in parallel with Triage)
    # ------------------------------------------------------------------
    investigate_task = Task(
        description=f"""
Investigate the root cause of this incident:

Incident ID: {incident_id}
Severity: {severity}
Primary namespace: {namespace}
Primary alert: {alertname}
Alert summary: {summary}

Steps:
1. Get pod logs for the primary pod in namespace '{namespace}'
2. Query Prometheus: memory usage, CPU usage, and pod restart counts for namespace '{namespace}'
3. If alert suggests OOMKilled: check memory usage vs limits
4. If alert suggests disk pressure: check node disk usage
5. If alert suggests high error rate: query error rate for relevant service
6. Form a root cause hypothesis with evidence from logs and metrics

Produce a root cause report:
- Root cause hypothesis (1-2 sentences)
- Evidence (log snippets, metric values that support the hypothesis)
- Confidence: High / Medium / Low
- Recommended remediation direction (do NOT execute anything — that is Mitigator's job)
        """,
        expected_output=(
            "A root cause report with: hypothesis (1-2 sentences), supporting evidence "
            "(logs + metrics), confidence level (High/Medium/Low), remediation direction."
        ),
        agent=investigator_agent,
    )

    # ------------------------------------------------------------------
    # Task 3: Mitigate (sequential — waits for triage + investigate)
    # ------------------------------------------------------------------
    mitigate_task = Task(
        description=f"""
Given the triage report and root cause investigation for incident {incident_id},
propose and (with human approval) apply the most appropriate remediation.

Context:
- Incident: {incident_id} ({severity}) — {title}
- Namespace: {namespace}

Steps:
1. Review the triage and investigation findings (from previous tasks)
2. Propose a specific remediation plan (e.g., restart deployment, scale up, increase memory limit)
3. Present the plan clearly: what you will do, why, and expected outcome
4. Execute the plan using the appropriate kubectl tool
   - restart_deployment: for CrashLoopBackOff / OOMKilled after config fix
   - scale_deployment: for capacity issues
   - patch_resource_limits: for OOMKilled with insufficient memory limits
   Note: REQUIRE_HUMAN_APPROVAL=true means you must wait for operator approval
5. Verify the fix: check pod status and logs again after the remediation

Produce a mitigation report:
- Action proposed
- Action taken (or "Pending human approval")
- Outcome / verification result
        """,
        expected_output=(
            "A mitigation report with: action proposed, action taken (or pending approval status), "
            "verification result (pod status after fix)."
        ),
        agent=mitigator_agent,
        context=[triage_task, investigate_task],
    )

    # ------------------------------------------------------------------
    # Task 4: Communicate (sequential — waits for mitigate)
    # ------------------------------------------------------------------
    communicate_task = Task(
        description=f"""
Based on the full incident response so far (triage, investigation, mitigation),
write and post a clear incident card to Slack.

Incident: {incident_id} ({severity}) — {title}

Steps:
1. Synthesise the triage report, root cause, and mitigation into a concise card
2. Use post_incident_card with this JSON structure:
{{
  "incident_id": "{incident_id}",
  "severity": "{severity}",
  "title": "<title>",
  "summary": "<2 sentences: what happened and root cause>",
  "affected_services": ["<service1>", "<service2>"],
  "recommended_actions": ["<action1>", "<action2>", "<action3>"],
  "status": "mitigating | resolved | monitoring"
}}
3. If the mitigation was successful, also use post_resolution_update with:
{{
  "incident_id": "{incident_id}",
  "action_taken": "<what the Mitigator did>",
  "result": "<outcome>",
  "status": "resolved"
}}
        """,
        expected_output=(
            "Confirmation that the incident card was posted to Slack, "
            "plus the text of the card that was sent."
        ),
        agent=communicator_agent,
        context=[triage_task, investigate_task, mitigate_task],
    )

    return [triage_task, investigate_task, mitigate_task, communicate_task]
