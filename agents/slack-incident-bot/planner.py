"""
planner.py — Anthropic SDK ReAct agent for the Slack Incident Bot.

Receives a raw alert ID, reasons over it with tool calls, and produces
a structured incident card posted to Slack.

LOOP
────
user: "New alert: {alert_id}. Analyse and post the incident card."
  │
  ▼
Claude calls get_alert_context(alert_id)
  │
  ▼ (tool result injected)
Claude calls post_incident_card(incident_id, severity, title, ...)
  │
  ▼ (tool result injected → "ok": true)
Claude stops (end_turn)

Usage
─────
    from planner import IncidentPlanner
    planner = IncidentPlanner(slack_client=app.client)
    planner.handle_alert("ALERT-001")
"""

from __future__ import annotations

import json
import os
from typing import Any

import anthropic

from memory import Memory, SYSTEM_PROMPT
from tools import TOOLS, TOOL_FUNCTIONS

# Safety cap: prevent runaway loops on unexpected LLM behaviour
MAX_ITERATIONS = 10


class PlannerConfig:
    model: str = "claude-haiku-4-5-20251001"
    max_tokens: int = 1024


class IncidentPlanner:
    """ReAct agent that analyses an alert and posts an incident card to Slack."""

    def __init__(
        self,
        slack_client: Any = None,
        channel_id: str | None = None,
        config: PlannerConfig | None = None,
    ) -> None:
        self._slack = slack_client
        self._channel_id = channel_id or os.environ.get("SLACK_CHANNEL_ID")
        self._config = config or PlannerConfig()
        self._client = anthropic.Anthropic()
        self._memory = Memory()

    def handle_alert(self, alert_id: str) -> dict[str, Any]:
        """Process a single alert end-to-end.

        Returns a dict with keys: incident_id, ts, status, iterations.
        Raises RuntimeError if the agent exceeds MAX_ITERATIONS.
        """
        self._memory.reset()
        user_msg = (
            f"New alert has fired: {alert_id}\n"
            "Analyse the alert context and post a structured incident card to Slack."
        )
        self._memory.add_user(user_msg)

        result: dict[str, Any] = {"incident_id": None, "ts": None, "status": "error"}
        iterations = 0

        while iterations < MAX_ITERATIONS:
            iterations += 1

            response = self._client.messages.create(
                model=self._config.model,
                max_tokens=self._config.max_tokens,
                system=SYSTEM_PROMPT,
                tools=TOOLS,
                messages=self._memory.messages,
            )

            self._memory.add_assistant(response.content)

            if response.stop_reason == "end_turn":
                result["status"] = "done"
                result["iterations"] = iterations
                return result

            if response.stop_reason != "tool_use":
                raise RuntimeError(
                    f"Unexpected stop_reason '{response.stop_reason}' after {iterations} iterations."
                )

            # Execute all tool calls in this response
            for block in response.content:
                if block.type != "tool_use":
                    continue

                tool_name = block.name
                tool_input = block.input
                tool_use_id = block.id

                tool_result = self._dispatch(tool_name, tool_input)
                self._memory.add_tool_result(tool_use_id, tool_result)

                # Extract ts/incident_id from post_incident_card result
                if tool_name == "post_incident_card":
                    try:
                        parsed = json.loads(tool_result)
                        result["ts"] = parsed.get("ts")
                        result["incident_id"] = parsed.get("incident_id")
                    except (json.JSONDecodeError, KeyError):
                        pass

        raise RuntimeError(
            f"Agent exceeded MAX_ITERATIONS ({MAX_ITERATIONS}) for alert {alert_id}."
        )

    def _dispatch(self, tool_name: str, tool_input: dict) -> str:
        """Route a tool call to the matching function, injecting the Slack client where needed."""
        fn = TOOL_FUNCTIONS.get(tool_name)
        if fn is None:
            return json.dumps({"error": f"Unknown tool: {tool_name}"})

        # Tools that need the Slack client receive it as a kwarg
        if tool_name in {"post_incident_card", "update_incident_card"}:
            return fn(
                **tool_input, slack_client=self._slack, channel_id=self._channel_id
            )

        return fn(**tool_input)
