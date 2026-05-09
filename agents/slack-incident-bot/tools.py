"""
tools.py — Anthropic SDK tool definitions for the Slack Incident Bot agent.

TOOLS
─────
get_alert_context     Return synthetic alert payload for a given alert ID.
post_incident_card    Post a new incident card to the configured Slack channel.
update_incident_card  Edit an existing incident card in-place by message timestamp.

DESIGN
──────
Tools follow the same registry pattern used in agents/log-intelligence:
- Each tool is a plain function with a matching SCHEMA dict.
- TOOLS list + TOOL_MAP dict are exported for the planner to consume.
- The Slack client is injected at call time (not module-level) so the module
  is fully importable and testable without real credentials.

SYNTHETIC ALERTS
────────────────
get_alert_context returns hard-coded payloads — no Prometheus/Datadog
integration yet. This lets the agent run end-to-end in dev without
a real monitoring stack. Replace with a real query in production.
"""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from typing import Any

# ── Synthetic alert store ─────────────────────────────────────────────────────

_SYNTHETIC_ALERTS: dict[str, dict[str, Any]] = {
    "ALERT-001": {
        "alert_id": "ALERT-001",
        "severity": "P1",
        "title": "DataNode replication factor below threshold",
        "service": "hdfs-namenode",
        "source": "Prometheus",
        "metric": "hdfs_under_replicated_blocks",
        "current_value": 1847,
        "threshold": 0,
        "triggered_at": "2024-05-08T08:42:00Z",
        "labels": {"cluster": "prod-hdfs", "node": "dn-03"},
        "runbook": "https://wiki.internal/hdfs-replication-recovery",
        "raw_logs_hint": "Check dn-03 disk usage and DataNode logs for IOExceptions",
    },
    "ALERT-002": {
        "alert_id": "ALERT-002",
        "severity": "P2",
        "title": "API gateway p99 latency > 2s",
        "service": "api-gateway",
        "source": "Datadog",
        "metric": "trace.web.request.duration.p99",
        "current_value": 2340,
        "threshold": 2000,
        "triggered_at": "2024-05-08T09:15:00Z",
        "labels": {"env": "production", "region": "us-east-1"},
        "runbook": "https://wiki.internal/api-latency-runbook",
        "raw_logs_hint": "Look for slow DB queries in the auth-service traces",
    },
    "ALERT-003": {
        "alert_id": "ALERT-003",
        "severity": "P3",
        "title": "Kubernetes pod restart loop — log-collector",
        "service": "log-collector",
        "source": "Prometheus",
        "metric": "kube_pod_container_status_restarts_total",
        "current_value": 12,
        "threshold": 5,
        "triggered_at": "2024-05-08T10:05:00Z",
        "labels": {"namespace": "logging", "pod": "log-collector-7d9f4"},
        "runbook": "https://wiki.internal/pod-crashloop-runbook",
        "raw_logs_hint": "kubectl logs log-collector-7d9f4 -n logging --previous",
    },
}


# ── Tool 1: get_alert_context ─────────────────────────────────────────────────

SCHEMA_GET_ALERT_CONTEXT = {
    "name": "get_alert_context",
    "description": (
        "Retrieve the full context for a firing alert by its alert ID. "
        "Returns severity, affected service, metric value, threshold, labels, "
        "and a hint about where to look in logs. Use this first to understand "
        "what the alert is about before composing the incident summary."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "alert_id": {
                "type": "string",
                "description": "The alert identifier, e.g. 'ALERT-001'.",
            }
        },
        "required": ["alert_id"],
    },
}


def get_alert_context(alert_id: str) -> str:
    """Return the alert payload as a JSON string."""
    payload = _SYNTHETIC_ALERTS.get(alert_id.upper())
    if payload is None:
        available = ", ".join(_SYNTHETIC_ALERTS.keys())
        return json.dumps(
            {
                "error": f"Alert '{alert_id}' not found.",
                "available_alert_ids": available,
            }
        )
    return json.dumps(payload, indent=2)


# ── Tool 2: post_incident_card ────────────────────────────────────────────────

SCHEMA_POST_INCIDENT_CARD = {
    "name": "post_incident_card",
    "description": (
        "Post a new structured incident card to the configured Slack channel. "
        "Call this once you have synthesised the root cause and suggested actions "
        "from the alert context. Returns the Slack message timestamp ('ts') which "
        "must be stored if you later need to update the card."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "incident_id": {
                "type": "string",
                "description": "Unique incident ID, e.g. 'INC-20240508-001'.",
            },
            "severity": {
                "type": "string",
                "enum": ["P1", "P2", "P3", "P4"],
                "description": "Incident severity level.",
            },
            "title": {
                "type": "string",
                "description": "One-line incident description (max 80 chars).",
            },
            "service": {
                "type": "string",
                "description": "Name of the affected service.",
            },
            "root_cause": {
                "type": "string",
                "description": (
                    "Your hypothesis for the root cause. Be specific: cite metric "
                    "values, affected components, and the likely failure chain."
                ),
            },
            "suggested_actions": {
                "type": "array",
                "items": {"type": "string"},
                "description": "Ordered list of concrete remediation steps (max 5).",
            },
        },
        "required": [
            "incident_id",
            "severity",
            "title",
            "service",
            "root_cause",
            "suggested_actions",
        ],
    },
}


def post_incident_card(
    incident_id: str,
    severity: str,
    title: str,
    service: str,
    root_cause: str,
    suggested_actions: list[str],
    slack_client: Any = None,
    channel_id: str | None = None,
) -> str:
    """Post the incident card to Slack and return the message ts."""
    from blocks import build_incident_card  # local import to avoid circular deps

    blocks = build_incident_card(
        incident_id=incident_id,
        severity=severity,
        title=title,
        service=service,
        root_cause=root_cause,
        suggested_actions=suggested_actions,
        status="open",
    )

    # ── Real Slack path ───────────────────────────────────────────────────────
    if slack_client is not None:
        ch = channel_id or os.environ.get("SLACK_CHANNEL_ID", "")
        if not ch:
            return json.dumps(
                {"error": "SLACK_CHANNEL_ID not set and no channel_id provided."}
            )
        try:
            resp = slack_client.chat_postMessage(channel=ch, blocks=blocks, text=title)
            ts = resp["ts"]
            return json.dumps({"ok": True, "ts": ts, "incident_id": incident_id})
        except Exception as exc:
            return json.dumps({"error": str(exc)})

    # ── Dry-run / test path ───────────────────────────────────────────────────
    fake_ts = f"{int(datetime.now(timezone.utc).timestamp())}.000000"
    return json.dumps(
        {
            "ok": True,
            "ts": fake_ts,
            "incident_id": incident_id,
            "note": "dry-run — no Slack client provided",
        }
    )


# ── Tool 3: update_incident_card ─────────────────────────────────────────────

SCHEMA_UPDATE_INCIDENT_CARD = {
    "name": "update_incident_card",
    "description": (
        "Update an existing incident card in Slack in-place using the message "
        "timestamp returned by post_incident_card. Use this to change the status "
        "after a human clicks Acknowledge, Escalate, or Dismiss."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "incident_id": {"type": "string"},
            "severity": {"type": "string", "enum": ["P1", "P2", "P3", "P4"]},
            "title": {"type": "string"},
            "service": {"type": "string"},
            "root_cause": {"type": "string"},
            "suggested_actions": {"type": "array", "items": {"type": "string"}},
            "status": {
                "type": "string",
                "enum": ["open", "acknowledged", "escalated", "dismissed", "resolved"],
                "description": "New status to reflect on the card.",
            },
            "actor": {
                "type": "string",
                "description": "Slack username of the person who triggered the update.",
            },
            "message_ts": {
                "type": "string",
                "description": "The 'ts' value returned by post_incident_card.",
            },
        },
        "required": [
            "incident_id",
            "severity",
            "title",
            "service",
            "root_cause",
            "suggested_actions",
            "status",
            "actor",
            "message_ts",
        ],
    },
}


def update_incident_card(
    incident_id: str,
    severity: str,
    title: str,
    service: str,
    root_cause: str,
    suggested_actions: list[str],
    status: str,
    actor: str,
    message_ts: str,
    slack_client: Any = None,
    channel_id: str | None = None,
) -> str:
    """Edit the existing Slack message in-place."""
    from blocks import build_status_update_card

    blocks = build_status_update_card(
        incident_id=incident_id,
        severity=severity,
        title=title,
        service=service,
        root_cause=root_cause,
        suggested_actions=suggested_actions,
        status=status,
        actor=actor,
    )

    if slack_client is not None:
        ch = channel_id or os.environ.get("SLACK_CHANNEL_ID", "")
        try:
            slack_client.chat_update(
                channel=ch, ts=message_ts, blocks=blocks, text=title
            )
            return json.dumps({"ok": True, "ts": message_ts, "status": status})
        except Exception as exc:
            return json.dumps({"error": str(exc)})

    return json.dumps(
        {
            "ok": True,
            "ts": message_ts,
            "status": status,
            "note": "dry-run — no Slack client provided",
        }
    )


# ── Exports ───────────────────────────────────────────────────────────────────

TOOLS = [
    SCHEMA_GET_ALERT_CONTEXT,
    SCHEMA_POST_INCIDENT_CARD,
    SCHEMA_UPDATE_INCIDENT_CARD,
]

TOOL_FUNCTIONS = {
    "get_alert_context": get_alert_context,
    "post_incident_card": post_incident_card,
    "update_incident_card": update_incident_card,
}
