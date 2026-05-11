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

OBSERVABILITY
─────────────
Two complementary layers, both optional and independently controlled:

1. LangSmith tracing (LANGSMITH_TRACING=true)
   Traces every handle_alert() call as a chain span with nested LLM runs:

     incident_planner.handle_alert  [chain]
       ├─ ChatAnthropic [llm]  ← get_alert_context turn
       └─ ChatAnthropic [llm]  ← post_incident_card turn

2. Prometheus metrics (METRICS_ENABLED=true, default)
   Exposes four metrics on http://localhost:METRICS_PORT/metrics:

     incident_bot_requests_total{status}        — alert throughput
     incident_bot_duration_seconds              — end-to-end latency
     incident_bot_tokens_total{direction}       — token cost proxy
     incident_bot_iterations_total              — ReAct loop efficiency

Usage
─────
    from planner import IncidentPlanner
    planner = IncidentPlanner(slack_client=app.client)
    planner.handle_alert("ALERT-001")
"""

from __future__ import annotations

import json
import os
import sys
import time
import uuid
from pathlib import Path
from typing import Any

import anthropic

from memory import Memory, SYSTEM_PROMPT
from metrics import record_duration, record_iterations, record_request, record_tokens
from tools import TOOLS, TOOL_FUNCTIONS
from tracing import init_tracing_client, ls_traceable

# Make the shared observability package importable from the repo root
sys.path.insert(0, str(Path(__file__).parent.parent.parent))
from observability import get_logger, set_correlation_id  # noqa: E402

log = get_logger(__name__, agent="slack-incident-bot")

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
        # wrap_anthropic auto-traces every messages.create() call to LangSmith
        # when tracing is enabled; falls back to plain client otherwise.
        self._client = init_tracing_client(anthropic.Anthropic())
        self._memory = Memory()

    @ls_traceable(
        name="incident_planner.handle_alert",
        run_type="chain",
        tags=["slack-incident-bot"],
    )
    def handle_alert(self, alert_id: str) -> dict[str, Any]:
        """Process a single alert end-to-end.

        Decorated with @ls_traceable so the full execution appears as a
        top-level chain run in LangSmith, with the two LLM turns nested
        underneath as child runs.

        Returns a dict with keys: incident_id, ts, status, iterations.
        Raises RuntimeError if the agent exceeds MAX_ITERATIONS.
        """
        cid = str(uuid.uuid4())
        set_correlation_id(cid)
        log.info("handle_alert started", extra={"alert_id": alert_id})

        self._memory.reset()
        user_msg = (
            f"New alert has fired: {alert_id}\n"
            "Analyse the alert context and post a structured incident card to Slack."
        )
        self._memory.add_user(user_msg)

        result: dict[str, Any] = {"incident_id": None, "ts": None, "status": "error"}
        iterations = 0
        _start = time.monotonic()

        try:
            while iterations < MAX_ITERATIONS:
                iterations += 1
                log.debug("ReAct iteration", extra={"alert_id": alert_id, "iteration": iterations})

                response = self._client.messages.create(
                    model=self._config.model,
                    max_tokens=self._config.max_tokens,
                    system=SYSTEM_PROMPT,
                    tools=TOOLS,
                    messages=self._memory.messages,
                )

                # ── Prometheus: record per-turn token usage ───────────────────
                if hasattr(response, "usage") and response.usage:
                    record_tokens(
                        prompt_tokens=response.usage.input_tokens,
                        completion_tokens=response.usage.output_tokens,
                    )

                self._memory.add_assistant(response.content)

                if response.stop_reason == "end_turn":
                    result["status"] = "done"
                    result["iterations"] = iterations
                    record_request("success")
                    record_iterations(iterations)
                    elapsed = time.monotonic() - _start
                    log.info(
                        "handle_alert completed",
                        extra={"alert_id": alert_id, "iterations": iterations, "duration_s": round(elapsed, 3)},
                    )
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

                    log.debug("Tool called", extra={"alert_id": alert_id, "tool": tool_name})
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

        except Exception as exc:
            log.error("handle_alert failed", extra={"alert_id": alert_id, "error": str(exc)})
            record_request("error")
            raise

        finally:
            # ── Prometheus: record total wall-clock duration ───────────────────
            record_duration(time.monotonic() - _start)

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
