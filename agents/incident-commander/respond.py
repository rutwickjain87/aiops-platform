#!/usr/bin/env python3
"""
Incident Commander — CLI entry point.

Usage:
  # Respond to an incident from the Alert Correlator output
  python respond.py --incident incidents.json

  # Respond to a single synthetic OOM incident (for demo/testing)
  python respond.py --demo oom

  # Respond to a single synthetic node pressure incident
  python respond.py --demo node_pressure

  # Skip the human approval gate (for CI/demo mode)
  REQUIRE_HUMAN_APPROVAL=false python respond.py --demo oom
"""
import os
import sys
import json
import argparse
import logging
from pathlib import Path
from datetime import datetime, timezone

from dotenv import load_dotenv

load_dotenv(Path(__file__).parent / ".env", override=True)

from rich.console import Console
from rich.panel import Panel

console = Console()

# ---------------------------------------------------------------------------
# Demo incidents — for testing without the Alert Correlator running
# ---------------------------------------------------------------------------

DEMO_INCIDENTS = {
    "oom": {
        "incident_id": f"INC-{datetime.now(timezone.utc).strftime('%Y%m%d')}-DEMO1",
        "title": "OOMKilled cascade in payments namespace",
        "severity": "critical",
        "alert_count": 3,
        "root_cause": None,
        "summary": None,
        "alert_ids": [1, 2, 3],
        "representative_alert": {
            "labels": {
                "alertname": "KubernetesContainerOOMKilled",
                "severity": "critical",
                "namespace": "payments",
                "pod": "payments-api-7d4f6b9c8-xk2pn",
                "container": "api",
            },
            "annotations": {
                "summary": "Container api in pod payments-api-7d4f6b9c8-xk2pn OOMKilled",
                "description": (
                    "Container has been OOMKilled 8 times in the last 10 minutes. "
                    "Memory limit: 512Mi. Current working set: 510Mi. "
                    "Related: HighErrorRate and HighLatencyP99 also firing."
                ),
            },
        },
    },
    "node_pressure": {
        "incident_id": f"INC-{datetime.now(timezone.utc).strftime('%Y%m%d')}-DEMO2",
        "title": "Node disk + memory pressure causing pod evictions",
        "severity": "critical",
        "alert_count": 4,
        "root_cause": None,
        "summary": None,
        "alert_ids": [10, 11, 12, 13],
        "representative_alert": {
            "labels": {
                "alertname": "NodeDiskPressure",
                "severity": "critical",
                "namespace": "monitoring",
                "node": "ip-10-0-1-42.eu-west-1.compute.internal",
            },
            "annotations": {
                "summary": "Node ip-10-0-1-42 disk pressure — 94% used",
                "description": (
                    "Node disk usage is at 94%. Kubelet has started evicting pods. "
                    "Prometheus pod (prometheus-7f9d4b8c5-2xvnq) evicted. "
                    "Metrics collection is interrupted."
                ),
            },
        },
    },
}


def main():
    parser = argparse.ArgumentParser(description="Incident Commander — 4-agent CrewAI response team")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--incident", "-i", help="Path to JSON file containing incident(s) from Alert Correlator")
    group.add_argument("--demo", choices=["oom", "node_pressure"], help="Run a demo incident")
    parser.add_argument("--verbose", "-v", action="store_true")
    args = parser.parse_args()

    if args.verbose:
        logging.basicConfig(level=logging.DEBUG, format="%(name)s %(levelname)s %(message)s")
    else:
        logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")

    # Suppress noisy CrewAI / LangChain internal loggers unless verbose
    if not args.verbose:
        for noisy in ("httpx", "openai", "anthropic", "crewai", "langchain"):
            logging.getLogger(noisy).setLevel(logging.WARNING)

    # Load incident(s)
    if args.demo:
        incidents = [DEMO_INCIDENTS[args.demo]]
        console.print(f"[dim]Running demo incident: {args.demo}[/dim]")
    else:
        with open(args.incident) as f:
            data = json.load(f)
        # Support both a single incident dict and a list
        incidents = data if isinstance(data, list) else [data]
        # Filter to only incidents (not raw correlator output)
        if "incidents" in incidents[0]:
            incidents = incidents[0]["incidents"]
        console.print(f"[dim]Loaded {len(incidents)} incident(s) from {args.incident}[/dim]")

    if not incidents:
        console.print("[yellow]No incidents to process.[/yellow]")
        sys.exit(0)

    from src.crew.crew import run_incident_commander

    for inc in incidents:
        console.print(Panel.fit(
            f"[bold red]🚨 Incident Commander activating[/bold red]\n"
            f"[bold]{inc.get('incident_id')}[/bold] [{inc.get('severity', '?').upper()}]\n"
            f"{inc.get('title', '')}",
            border_style="red",
        ))

        result = run_incident_commander(inc)

        if result["status"] == "completed":
            console.print(Panel(
                f"[bold green]✅ Incident response complete[/bold green]\n\n"
                f"{result.get('crew_output', '')[:500]}",
                border_style="green",
                title=result["incident_id"],
            ))
        else:
            console.print(Panel(
                f"[bold red]❌ Crew failed[/bold red]\n"
                f"Errors: {result.get('errors')}",
                border_style="red",
            ))

        if len(incidents) > 1:
            console.print("\n" + "─" * 60 + "\n")


if __name__ == "__main__":
    main()
