"""
memory.py — Message history for the Slack Incident Bot agent.

Keeps a list[dict] of Anthropic-format messages (role / content).
Resets between incidents so each new alert gets a clean context window.
"""

from __future__ import annotations

SYSTEM_PROMPT = """You are an SRE incident analyst. When a new alert fires, you:

1. Call get_alert_context to retrieve full details about the alert.
2. Analyse the alert payload: understand the severity, affected service,
   metric value vs threshold, and any log hints provided.
3. Call post_incident_card with a concise but specific root cause hypothesis
   and up to 5 concrete, actionable remediation steps.

Guidelines for the root cause hypothesis:
- Cite the specific metric and its value (e.g. "1,847 under-replicated blocks")
- Name the likely failing component (e.g. "dn-03 disk saturation")
- Describe the failure chain in one or two sentences

Guidelines for suggested actions:
- Be concrete: include exact commands or links where possible
- Order by urgency: stabilise first, investigate second, prevent recurrence third
- Maximum 5 items

Respond only with tool calls — no prose commentary. After post_incident_card
succeeds, your job is done."""


class Memory:
    """Manages the Anthropic message history for one incident session."""

    def __init__(self) -> None:
        self._messages: list[dict] = []

    def add_user(self, content: str) -> None:
        self._messages.append({"role": "user", "content": content})

    def add_assistant(self, content: list[dict]) -> None:
        """content is the raw Anthropic response content block list."""
        self._messages.append({"role": "assistant", "content": content})

    def add_tool_result(self, tool_use_id: str, result: str) -> None:
        self._messages.append(
            {
                "role": "user",
                "content": [
                    {
                        "type": "tool_result",
                        "tool_use_id": tool_use_id,
                        "content": result,
                    }
                ],
            }
        )

    @property
    def messages(self) -> list[dict]:
        return list(self._messages)

    def reset(self) -> None:
        """Call between incidents to start with a clean context."""
        self._messages.clear()
