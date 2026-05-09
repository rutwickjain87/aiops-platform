"""
handlers.py — Slack action handlers for the three incident buttons.

Each handler is registered with the Bolt app in bot.py via:
    app.action("acknowledge_incident")(handlers.acknowledge)

All three handlers follow the same pattern:
1. Acknowledge the action immediately (Slack requires a response within 3 s)
2. Parse the incident_id from action["value"]
3. Look up the stored incident state from INCIDENT_STORE
4. Call update_incident_card to edit the Slack message in-place
5. Update the store to reflect the new status

INCIDENT_STORE
──────────────
An in-process dict mapping incident_id → state dict. In production this
would be Redis or a database so state survives bot restarts.
"""

from __future__ import annotations

import logging
from typing import Any

from tools import update_incident_card

logger = logging.getLogger(__name__)

# In-memory store: incident_id → {ts, severity, title, service, root_cause, suggested_actions}
INCIDENT_STORE: dict[str, dict[str, Any]] = {}


def _get_incident(incident_id: str) -> dict[str, Any] | None:
    return INCIDENT_STORE.get(incident_id)


def _update_card(body: dict, client: Any, status: str) -> None:
    """Shared logic for all three button handlers."""
    action = body["actions"][0]
    incident_id = action["value"]
    actor = body["user"]["username"]

    incident = _get_incident(incident_id)
    if incident is None:
        logger.warning("Unknown incident_id in button click: %s", incident_id)
        return

    result = update_incident_card(
        incident_id=incident_id,
        severity=incident["severity"],
        title=incident["title"],
        service=incident["service"],
        root_cause=incident["root_cause"],
        suggested_actions=incident["suggested_actions"],
        status=status,
        actor=actor,
        message_ts=incident["ts"],
        slack_client=client,
        channel_id=incident.get("channel_id"),
    )

    # Persist the new status so subsequent button clicks see updated state
    INCIDENT_STORE[incident_id]["status"] = status
    logger.info(
        "Incident %s → %s by %s | result: %s", incident_id, status, actor, result
    )


def acknowledge(body: dict, ack, client: Any) -> None:
    """Handle ✅ Acknowledge button."""
    ack()
    _update_card(body, client, status="acknowledged")


def escalate(body: dict, ack, client: Any) -> None:
    """Handle 🚨 Escalate button."""
    ack()
    _update_card(body, client, status="escalated")


def dismiss(body: dict, ack, client: Any) -> None:
    """Handle ❌ Dismiss button."""
    ack()
    _update_card(body, client, status="dismissed")
