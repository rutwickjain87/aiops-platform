"""
blocks.py — Slack Block Kit builder for incident cards.

Produces the Block Kit JSON that renders as a rich incident card in Slack.
All functions return plain Python dicts — no Slack SDK dependency here,
so the module is fully testable without credentials.

Card anatomy
─────────────
┌─────────────────────────────────────────────────┐
│ 🔴 P1 — DataNode replication failure            │  (header)
│ Service: hdfs-namenode  |  08:42 UTC            │  (fields)
│ ─────────────────────────────────────────────── │
│ Root Cause Hypothesis                           │  (section)
│ DataNode disk saturation on dn-03 causing...    │
│ ─────────────────────────────────────────────── │
│ Suggested Actions                               │  (section)
│ • Drain dn-03 via hdfs dfsadmin -decommission   │
│ • Check disk usage: df -h /data                 │
│ ─────────────────────────────────────────────── │
│ [✅ Acknowledge]  [🚨 Escalate]  [❌ Dismiss]   │  (actions)
│ Status: Open  |  ID: INC-20240508-001           │  (context)
└─────────────────────────────────────────────────┘
"""

from __future__ import annotations

from datetime import datetime, timezone

# Severity → (emoji, colour for sidebar)
SEVERITY_META: dict[str, tuple[str, str]] = {
    "P1": ("🔴", "danger"),
    "P2": ("🟠", "warning"),
    "P3": ("🟡", "warning"),
    "P4": ("🔵", "good"),
}

STATUS_EMOJI = {
    "open": "🟢",
    "acknowledged": "👀",
    "escalated": "🚨",
    "dismissed": "❌",
    "resolved": "✅",
}


def _severity_emoji(severity: str) -> str:
    return SEVERITY_META.get(severity.upper(), ("⚪", ""))[0]


def build_incident_card(
    incident_id: str,
    severity: str,
    title: str,
    service: str,
    root_cause: str,
    suggested_actions: list[str],
    status: str = "open",
    timestamp: datetime | None = None,
) -> list[dict]:
    """Return a Block Kit block list for a new or updated incident card.

    Args:
        incident_id: Unique incident identifier, e.g. 'INC-20240508-001'.
        severity:     P1 / P2 / P3 / P4.
        title:        One-line incident description.
        service:      Affected service name.
        root_cause:   LLM-generated root cause hypothesis (one paragraph).
        suggested_actions: Ordered list of remediation steps.
        status:       open | acknowledged | escalated | dismissed | resolved.
        timestamp:    UTC datetime of the incident. Defaults to now.
    """
    if timestamp is None:
        timestamp = datetime.now(timezone.utc)

    ts_str = timestamp.strftime("%H:%M UTC  %d %b %Y")
    emoji = _severity_emoji(severity)
    sev_upper = severity.upper()
    status_display = f"{STATUS_EMOJI.get(status, '⚪')} {status.capitalize()}"

    # Build bullet list for suggested actions
    actions_text = (
        "\n".join(f"• {a}" for a in suggested_actions)
        if suggested_actions
        else "_No actions suggested._"
    )

    blocks: list[dict] = [
        # ── Header ──────────────────────────────────────────────────────────
        {
            "type": "header",
            "text": {
                "type": "plain_text",
                "text": f"{emoji} {sev_upper} — {title}",
                "emoji": True,
            },
        },
        # ── Service / timestamp fields ───────────────────────────────────────
        {
            "type": "section",
            "fields": [
                {"type": "mrkdwn", "text": f"*Service:*\n{service}"},
                {"type": "mrkdwn", "text": f"*Time:*\n{ts_str}"},
            ],
        },
        {"type": "divider"},
        # ── Root cause ───────────────────────────────────────────────────────
        {
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": f"*🔍 Root Cause Hypothesis*\n{root_cause}",
            },
        },
        {"type": "divider"},
        # ── Suggested actions ────────────────────────────────────────────────
        {
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": f"*🛠 Suggested Actions*\n{actions_text}",
            },
        },
        {"type": "divider"},
        # ── Action buttons ───────────────────────────────────────────────────
        {
            "type": "actions",
            "block_id": f"incident_actions_{incident_id}",
            "elements": [
                {
                    "type": "button",
                    "text": {
                        "type": "plain_text",
                        "text": "✅ Acknowledge",
                        "emoji": True,
                    },
                    "style": "primary",
                    "action_id": "acknowledge_incident",
                    "value": incident_id,
                },
                {
                    "type": "button",
                    "text": {
                        "type": "plain_text",
                        "text": "🚨 Escalate",
                        "emoji": True,
                    },
                    "style": "danger",
                    "action_id": "escalate_incident",
                    "value": incident_id,
                },
                {
                    "type": "button",
                    "text": {"type": "plain_text", "text": "❌ Dismiss", "emoji": True},
                    "action_id": "dismiss_incident",
                    "value": incident_id,
                },
            ],
        },
        # ── Context footer ───────────────────────────────────────────────────
        {
            "type": "context",
            "elements": [
                {
                    "type": "mrkdwn",
                    "text": f"*Status:* {status_display}   |   *ID:* `{incident_id}`",
                }
            ],
        },
    ]

    return blocks


def build_status_update_card(
    incident_id: str,
    severity: str,
    title: str,
    service: str,
    root_cause: str,
    suggested_actions: list[str],
    status: str,
    actor: str,
    timestamp: datetime | None = None,
) -> list[dict]:
    """Same as build_incident_card but appends an update note and hides the action buttons.

    Used when a button has been clicked — the card is locked to prevent double-clicks.
    """
    blocks = build_incident_card(
        incident_id=incident_id,
        severity=severity,
        title=title,
        service=service,
        root_cause=root_cause,
        suggested_actions=suggested_actions,
        status=status,
        timestamp=timestamp,
    )

    # Replace the actions block with a plain update note so buttons disappear
    blocks = [b for b in blocks if b.get("type") != "actions"]
    blocks.append(
        {
            "type": "context",
            "elements": [
                {
                    "type": "mrkdwn",
                    "text": (
                        f"*Updated by* @{actor} · "
                        f"{datetime.now(timezone.utc).strftime('%H:%M UTC %d %b %Y')}"
                    ),
                }
            ],
        }
    )

    return blocks
