#!/usr/bin/env python3
"""
Alert Correlator — CLI entry point.

Usage:
  # Correlate a saved AlertManager payload from a file
  python correlate.py --input alerts.json

  # Generate synthetic alerts and correlate them in one shot
  python correlate.py --scenario oom_cascade

  # Generate mixed (correlated + noise) alerts
  python correlate.py --scenario mixed

  # Pretty-print result and also save JSON output
  python correlate.py --scenario node_pressure --output result.json
"""
import sys
import json
import argparse
import logging
from pathlib import Path

from dotenv import load_dotenv

load_dotenv(Path(__file__).parent / ".env", override=True)

from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich import print as rprint

from src.graph.graph import graph

console = Console()


def _severity_colour(sev: str) -> str:
    return {"critical": "red", "error": "dark_orange", "warning": "yellow", "info": "cyan"}.get(sev, "white")


def print_result(result: dict) -> None:
    stats = result.get("stats", {})
    incidents = result.get("incidents", [])
    errors = result.get("errors", [])

    console.print(Panel.fit(
        f"[bold]Alert Correlator[/bold] — pipeline complete\n"
        f"Parsed: {stats.get('parsed', 0)}  Embedded: {stats.get('embedded', 0)}  "
        f"Similar found: {stats.get('similar_found', 0)}  "
        f"Clusters: {stats.get('clusters', 0)}  Incidents: {stats.get('incidents', 0)}",
        border_style="blue",
    ))

    if not incidents:
        console.print("[yellow]No incidents generated (no correlated alert clusters found)[/yellow]")
    else:
        for inc in incidents:
            sev = inc["severity"]
            colour = _severity_colour(sev)
            console.print(Panel(
                f"[bold {colour}]{inc['incident_id']}[/bold {colour}]  [{colour}]{sev.upper()}[/{colour}]\n\n"
                f"[bold]{inc['title']}[/bold]\n\n"
                f"[dim]Root cause:[/dim] {inc.get('root_cause', '')}\n\n"
                f"[dim]Summary:[/dim] {inc.get('summary', '')}\n\n"
                f"Alert count: {inc['alert_count']}  |  Alert IDs: {inc['alert_ids']}",
                border_style=colour,
            ))

    if errors:
        console.print(f"\n[dim red]Errors ({len(errors)}):[/dim red]")
        for e in errors:
            console.print(f"  [dim red]• {e}[/dim red]")


def main():
    parser = argparse.ArgumentParser(description="Alert Correlator — pgvector + Voyage AI + LangGraph")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--input", "-i", help="Path to AlertManager JSON payload file")
    group.add_argument("--scenario", "-s",
                       choices=["oom_cascade", "node_pressure", "security_incident", "noise", "mixed"],
                       help="Generate synthetic alerts for the given scenario")
    parser.add_argument("--output", "-o", help="Save full pipeline result to this JSON file")
    parser.add_argument("--verbose", "-v", action="store_true")
    args = parser.parse_args()

    if args.verbose:
        logging.basicConfig(level=logging.DEBUG, format="%(name)s %(levelname)s %(message)s")
    else:
        logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")

    # Load or generate alerts
    if args.input:
        with open(args.input) as f:
            raw_alerts = json.load(f)
        console.print(f"[dim]Loaded {len(raw_alerts)} alerts from {args.input}[/dim]")
    else:
        sys.path.insert(0, str(Path(__file__).parent))
        from synthetic.generate_alerts import generate_scenario, generate_mixed
        if args.scenario == "mixed":
            raw_alerts = generate_mixed()
        else:
            raw_alerts = generate_scenario(args.scenario)
        console.print(f"[dim]Generated {len(raw_alerts)} synthetic alerts (scenario: {args.scenario})[/dim]")

    # Run the LangGraph pipeline
    initial_state = {
        "raw_alerts": raw_alerts,
        "parsed_alerts": [],
        "embedded_alerts": [],
        "similarity_groups": [],
        "clusters": [],
        "incidents": [],
        "errors": [],
        "stats": {},
    }

    console.print("[dim]Running correlation pipeline...[/dim]")
    result = graph.invoke(initial_state)

    print_result(result)

    if args.output:
        # Incidents are JSON-serialisable (no numpy arrays after conversion)
        out = {
            "stats": result.get("stats"),
            "incidents": result.get("incidents"),
            "errors": result.get("errors"),
        }
        with open(args.output, "w") as f:
            json.dump(out, f, indent=2, default=str)
        console.print(f"\n[green]Result saved to {args.output}[/green]")


if __name__ == "__main__":
    main()
