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
you MUST propose AND then actually call a kubectl tool to apply the remediation.
Do NOT just describe what you would do — you must invoke the tool.

Context:
- Incident: {incident_id} ({severity}) — {title}
- Namespace: {namespace}

Steps:
1. Review the triage and investigation findings (from previous tasks)
2. Check what deployments exist: call get_deployment_status with namespace '{namespace}'
3. Choose the correct mutating tool and CALL IT — do not just write about it:
   - patch_resource_limits: FIRST choice for OOMKilled — increases memory limit
     Input: "<namespace>/<deployment-name>/<new-memory-limit>" e.g. "{namespace}/oom-demo/256Mi"
   - restart_deployment: for CrashLoopBackOff where config is already correct
     Input: "<namespace>/<deployment-name>"
   - scale_deployment: for capacity/replica issues
     Input: "<namespace>/<deployment-name>/<replica-count>"
4. The tool will pause and ask for human approval at the terminal — this is expected.
   Wait for the operator to type yes or no before continuing.
5. After the tool returns, verify by calling get_pods_in_namespace('{namespace}')

IMPORTANT: You MUST call at least one of patch_resource_limits, restart_deployment,
or scale_deployment. Writing "I would patch the limits" is NOT sufficient —
you must actually invoke the tool.

Produce a mitigation report:
- Deployment found (name)
- Tool called (exact tool name and input)
- Approval decision (approved / rejected)
- Outcome / verification result (pod status after fix)
        """,
        expected_output=(
            "A mitigation report confirming: which deployment was found, which tool was called "
            "with what input, whether the operator approved, and the pod status after the action."
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
