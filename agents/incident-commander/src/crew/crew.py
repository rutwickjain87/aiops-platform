"""
Incident Commander crew — wires agents + tasks into a CrewAI Crew.

Execution model:
  - Tasks 1 (triage) and 2 (investigate) run in parallel
  - Task 3 (mitigate) is sequential, waits for 1+2
  - Task 4 (communicate) is sequential, waits for 3

CrewAI process=Process.sequential handles this via task `context` dependencies.
"""
import os
import logging
from crewai import Crew, Process

from ..agents.agents import (
    triage_agent, investigator_agent, mitigator_agent, communicator_agent
)
from .tasks import build_tasks

log = logging.getLogger(__name__)


def run_incident_commander(incident: dict) -> dict:
    """
    Run the full 4-agent Incident Commander crew for a given incident.
    Returns a dict with the crew output and any errors.
    """
    log.info(
        "Starting Incident Commander for %s [%s] — %s",
        incident.get("incident_id"),
        incident.get("severity"),
        incident.get("title"),
    )

    tasks = build_tasks(incident)

    # Triage + Investigate run in parallel; CrewAI achieves this via
    # the context dependency graph when process=Process.sequential.
    # Tasks 1+2 have no context (no dependencies) so they can overlap.
    # Tasks 3+4 have context → they wait.
    crew = Crew(
        agents=[triage_agent, investigator_agent, mitigator_agent, communicator_agent],
        tasks=tasks,
        process=Process.sequential,
        verbose=True,
        memory=False,  # No cross-run memory — incidents are self-contained
    )

    try:
        result = crew.kickoff()
        return {
            "status": "completed",
            "incident_id": incident.get("incident_id"),
            "crew_output": str(result),
            "errors": [],
        }
    except Exception as exc:
        log.error("Crew failed for %s: %s", incident.get("incident_id"), exc)
        return {
            "status": "failed",
            "incident_id": incident.get("incident_id"),
            "crew_output": None,
            "errors": [str(exc)],
        }
