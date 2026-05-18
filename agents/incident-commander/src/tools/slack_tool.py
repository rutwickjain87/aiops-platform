"""
Slack notification tool for the Incident Communicator agent.
Posts structured incident cards to the incidents channel.
"""
import os
import json
import logging
import requests
from crewai.tools import tool

log = logging.getLogger(__name__)

SLACK_TOKEN = os.environ.get("SLACK_BOT_TOKEN", "")
SLACK_CHANNEL = os.environ.get("SLACK_INCIDENT_CHANNEL", "#incidents")


def _post_message(blocks: list, text: str) -> str:
    if not SLACK_TOKEN:
        # In development, just pretty-print what would be sent
        log.info("SLACK_BOT_TOKEN not set — printing card instead of posting")
        print("\n[SLACK INCIDENT CARD - dev mode]\n")
        print(f"Channel: {SLACK_CHANNEL}")
        print(f"Text: {text}")
        print("Blocks:")
        print(json.dumps(blocks, indent=2))
        return "OK (dev mode — printed to stdout)"

    try:
        resp = requests.post(
            "https://slack.com/api/chat.postMessage",
            headers={"Authorization": f"Bearer {SLACK_TOKEN}", "Content-Type": "application/json"},
            json={"channel": SLACK_CHANNEL, "text": text, "blocks": blocks},
            timeout=10,
        )
        data = resp.json()
        if data.get("ok"):
            return f"Message posted to {SLACK_CHANNEL} (ts={data.get('ts')})"
        return f"Slack error: {data.get('error', 'unknown')}"
    except Exception as exc:
        return f"ERROR posting to Slack: {exc}"


@tool("post_incident_card")
def post_incident_card(incident_json: str) -> str:
    """
    Post a structured incident card to the Slack incidents channel.
    Input: JSON string with keys: incident_id, severity, title, summary,
    affected_services, recommended_actions, status.
    """
    try:
        inc = json.loads(incident_json)
    except json.JSONDecodeError as exc:
        return f"ERROR: invalid JSON input: {exc}"

    severity = inc.get("severity", "warning").upper()
    emoji = {"CRITICAL": "🔴", "ERROR": "🟠", "WARNING": "🟡", "INFO": "🔵"}.get(severity, "⚪")
    incident_id = inc.get("incident_id", "INC-UNKNOWN")
    title = inc.get("title", "Untitled Incident")
    summary = inc.get("summary", "")
    services = inc.get("affected_services", [])
    actions = inc.get("recommended_actions", [])
    status = inc.get("status", "investigating")

    blocks = [
        {
            "type": "header",
            "text": {"type": "plain_text", "text": f"{emoji} {incident_id} — {severity}"},
        },
        {
            "type": "section",
            "text": {"type": "mrkdwn", "text": f"*{title}*"},
        },
        {"type": "divider"},
        {
            "type": "section",
            "fields": [
                {"type": "mrkdwn", "text": f"*Status:*\n{status}"},
                {"type": "mrkdwn", "text": f"*Affected:*\n{', '.join(services) if services else 'Unknown'}"},
            ],
        },
    ]

    if summary:
        blocks.append({
            "type": "section",
            "text": {"type": "mrkdwn", "text": f"*Summary:*\n{summary}"},
        })

    if actions:
        action_text = "\n".join(f"• {a}" for a in actions)
        blocks.append({
            "type": "section",
            "text": {"type": "mrkdwn", "text": f"*Recommended Actions:*\n{action_text}"},
        })

    blocks.append({"type": "divider"})
    blocks.append({
        "type": "context",
        "elements": [{"type": "mrkdwn", "text": "Powered by AIOps Incident Commander · LangGraph + CrewAI"}],
    })

    text = f"{emoji} {incident_id} {severity} — {title}"
    return _post_message(blocks, text)


@tool("post_resolution_update")
def post_resolution_update(update_json: str) -> str:
    """
    Post a resolution update to the Slack incidents channel.
    Input: JSON string with keys: incident_id, action_taken, result, status.
    """
    try:
        upd = json.loads(update_json)
    except json.JSONDecodeError as exc:
        return f"ERROR: invalid JSON input: {exc}"

    incident_id = upd.get("incident_id", "INC-UNKNOWN")
    action = upd.get("action_taken", "")
    result = upd.get("result", "")
    status = upd.get("status", "resolved")

    emoji = "✅" if status == "resolved" else "🔄"
    blocks = [
        {
            "type": "section",
            "text": {"type": "mrkdwn",
                     "text": f"{emoji} *{incident_id} Update*\n*Status:* {status}\n*Action:* {action}\n*Result:* {result}"},
        }
    ]
    return _post_message(blocks, f"{emoji} {incident_id} — {status}")
