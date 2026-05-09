"""
bot.py — Slack Socket Mode entry point for the AIOps Incident Bot.

ARCHITECTURE
────────────
                  ┌─────────────────────────────────────────┐
  Prometheus ───▶ │  bot.py trigger_alert(alert_id)         │
  (simulated)     │                                         │
                  │  IncidentPlanner.handle_alert(alert_id) │
                  │    ├─ get_alert_context                 │
                  │    └─ post_incident_card ──────────────▶│ Slack #incidents
                  │                                         │      │
                  │  [User clicks button in Slack]          │◀─────┘
                  │    ├─ acknowledge_incident              │
                  │    ├─ escalate_incident                 │
                  │    └─ dismiss_incident                  │
                  └─────────────────────────────────────────┘

RUNNING LOCALLY
───────────────
1. Copy .env.example to .env and fill in the three Slack tokens + Anthropic key
2. uv venv .venv && uv pip install -r requirements.txt
3. source .venv/bin/activate
4. python bot.py                      # starts Socket Mode listener
5. python bot.py --trigger ALERT-001  # fire a test alert immediately + listen

TRIGGERING ALERTS PROGRAMMATICALLY
────────────────────────────────────
In production a Prometheus Alertmanager webhook → FastAPI endpoint calls
trigger_alert(). For the demo, use the --trigger flag or import and call:

    from bot import trigger_alert
    trigger_alert("ALERT-002")
"""

from __future__ import annotations

import argparse
import logging
import os

from dotenv import load_dotenv
from slack_bolt import App
from slack_bolt.adapter.socket_mode import SocketModeHandler

import handlers
from handlers import INCIDENT_STORE
from planner import IncidentPlanner

load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(name)s  %(message)s",
)
logger = logging.getLogger("slack-incident-bot")

# ── Bolt app (uses SLACK_BOT_TOKEN from env) ──────────────────────────────────

app = App(token=os.environ.get("SLACK_BOT_TOKEN"))

# ── Register action handlers ──────────────────────────────────────────────────

app.action("acknowledge_incident")(handlers.acknowledge)
app.action("escalate_incident")(handlers.escalate)
app.action("dismiss_incident")(handlers.dismiss)

# ── Planner (shared instance; stateless between calls) ────────────────────────

_planner = IncidentPlanner(
    slack_client=app.client,
    channel_id=os.environ.get("SLACK_CHANNEL_ID"),
)


# ── Public trigger function ───────────────────────────────────────────────────


def trigger_alert(alert_id: str) -> dict:
    """Fire an alert through the planner and store the result in INCIDENT_STORE.

    Returns the planner result dict {incident_id, ts, status, iterations}.
    """
    logger.info("Triggering alert: %s", alert_id)
    result = _planner.handle_alert(alert_id)
    incident_id = result.get("incident_id")
    ts = result.get("ts")

    if incident_id and ts:
        # Bootstrap INCIDENT_STORE with enough data for button handlers to update the card.
        # In a real system this would be persisted to Redis/DB.
        from tools import get_alert_context
        import json

        raw = json.loads(get_alert_context(alert_id))
        INCIDENT_STORE[incident_id] = {
            "ts": ts,
            "severity": raw.get("severity", "P3"),
            "title": raw.get("title", alert_id),
            "service": raw.get("service", "unknown"),
            "root_cause": "(see card)",  # populated by the LLM in the card
            "suggested_actions": [],  # populated by the LLM in the card
            "channel_id": os.environ.get("SLACK_CHANNEL_ID"),
            "status": "open",
        }
        logger.info(
            "Incident %s posted (ts=%s) in %d iterations",
            incident_id,
            ts,
            result.get("iterations", -1),
        )
    else:
        logger.warning(
            "Planner did not return incident_id/ts for alert %s: %s", alert_id, result
        )

    return result


# ── CLI entry point ───────────────────────────────────────────────────────────


def main() -> None:
    parser = argparse.ArgumentParser(description="AIOps Slack Incident Bot")
    parser.add_argument(
        "--trigger",
        metavar="ALERT_ID",
        help="Fire this alert immediately on startup (e.g. ALERT-001), then keep listening.",
    )
    args = parser.parse_args()

    if args.trigger:
        trigger_alert(args.trigger)

    logger.info("Starting Socket Mode listener…")
    handler = SocketModeHandler(app, os.environ.get("SLACK_APP_TOKEN"))
    handler.start()


if __name__ == "__main__":
    main()
