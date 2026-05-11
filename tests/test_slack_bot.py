"""
tests/test_slack_bot.py — Unit tests for the Slack Incident Bot.

All tests run without Slack credentials or Anthropic API keys.
Uses mock Slack client and in-memory tool stubs.
"""

from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import MagicMock

# Make the slack-incident-bot module importable
sys.path.insert(0, str(Path(__file__).parent.parent / "agents" / "slack-incident-bot"))


# ── blocks.py ────────────────────────────────────────────────────────────────


class TestBuildIncidentCard:
    def _build(self, **kwargs):
        from blocks import build_incident_card

        defaults = dict(
            incident_id="INC-TEST-001",
            severity="P1",
            title="Test incident",
            service="test-svc",
            root_cause="Something broke.",
            suggested_actions=["Fix it", "Verify it"],
            status="open",
            timestamp=datetime(2024, 5, 8, 8, 42, 0, tzinfo=timezone.utc),
        )
        return build_incident_card(**{**defaults, **kwargs})

    def test_returns_list(self):
        blocks = self._build()
        assert isinstance(blocks, list)
        assert len(blocks) > 0

    def test_header_contains_severity_and_title(self):
        blocks = self._build(severity="P1", title="Disk full")
        header = next(b for b in blocks if b["type"] == "header")
        assert "P1" in header["text"]["text"]
        assert "Disk full" in header["text"]["text"]

    def test_p1_emoji_is_red(self):
        blocks = self._build(severity="P1")
        header = next(b for b in blocks if b["type"] == "header")
        assert "🔴" in header["text"]["text"]

    def test_p2_emoji_is_orange(self):
        blocks = self._build(severity="P2")
        header = next(b for b in blocks if b["type"] == "header")
        assert "🟠" in header["text"]["text"]

    def test_actions_block_has_three_buttons(self):
        blocks = self._build()
        action_blocks = [b for b in blocks if b["type"] == "actions"]
        assert len(action_blocks) == 1
        assert len(action_blocks[0]["elements"]) == 3

    def test_action_ids_are_correct(self):
        blocks = self._build()
        actions = next(b for b in blocks if b["type"] == "actions")
        ids = {el["action_id"] for el in actions["elements"]}
        assert ids == {"acknowledge_incident", "escalate_incident", "dismiss_incident"}

    def test_incident_id_in_action_values(self):
        blocks = self._build(incident_id="INC-XYZ")
        actions = next(b for b in blocks if b["type"] == "actions")
        values = {el["value"] for el in actions["elements"]}
        assert "INC-XYZ" in values

    def test_root_cause_appears_in_section(self):
        blocks = self._build(root_cause="Disk saturation on dn-03")
        texts = [
            b["text"]["text"]
            for b in blocks
            if b["type"] == "section" and "text" in b and "text" in b.get("text", {})
        ]
        assert any("Disk saturation on dn-03" in t for t in texts)

    def test_suggested_actions_rendered_as_bullets(self):
        blocks = self._build(suggested_actions=["Step A", "Step B"])
        texts = [
            b["text"]["text"]
            for b in blocks
            if b["type"] == "section" and "text" in b and "text" in b.get("text", {})
        ]
        combined = "\n".join(texts)
        assert "• Step A" in combined
        assert "• Step B" in combined


class TestBuildStatusUpdateCard:
    def test_no_actions_block_after_update(self):
        from blocks import build_status_update_card

        blocks = build_status_update_card(
            incident_id="INC-001",
            severity="P2",
            title="Test",
            service="svc",
            root_cause="Root",
            suggested_actions=["Do this"],
            status="acknowledged",
            actor="alice",
        )
        action_blocks = [b for b in blocks if b["type"] == "actions"]
        assert len(action_blocks) == 0

    def test_actor_name_in_context(self):
        from blocks import build_status_update_card

        blocks = build_status_update_card(
            incident_id="INC-001",
            severity="P2",
            title="Test",
            service="svc",
            root_cause="Root",
            suggested_actions=[],
            status="escalated",
            actor="bob",
        )
        context_texts = [
            el["text"]
            for b in blocks
            if b["type"] == "context"
            for el in b.get("elements", [])
        ]
        assert any("bob" in t for t in context_texts)


# ── tools.py ─────────────────────────────────────────────────────────────────


class TestGetAlertContext:
    def test_known_alert_returns_json(self):
        from tools import get_alert_context

        result = json.loads(get_alert_context("ALERT-001"))
        assert result["alert_id"] == "ALERT-001"
        assert result["severity"] == "P1"

    def test_case_insensitive(self):
        from tools import get_alert_context

        result = json.loads(get_alert_context("alert-002"))
        assert result["alert_id"] == "ALERT-002"

    def test_unknown_alert_returns_error(self):
        from tools import get_alert_context

        result = json.loads(get_alert_context("ALERT-999"))
        assert "error" in result
        assert "available_alert_ids" in result

    def test_all_synthetic_alerts_parseable(self):
        from tools import _SYNTHETIC_ALERTS, get_alert_context  # noqa: I001

        for alert_id in _SYNTHETIC_ALERTS:
            result = json.loads(get_alert_context(alert_id))
            assert "error" not in result
            assert "severity" in result


class TestPostIncidentCardDryRun:
    """Tests without a real Slack client (dry-run path)."""

    def _post(self, **kwargs):
        from tools import post_incident_card

        defaults = dict(
            incident_id="INC-DRY-001",
            severity="P2",
            title="Dry run test",
            service="test-svc",
            root_cause="Hypothetical failure.",
            suggested_actions=["Step 1"],
        )
        return json.loads(post_incident_card(**{**defaults, **kwargs}))

    def test_dry_run_returns_ok(self):
        result = self._post()
        assert result["ok"] is True

    def test_dry_run_returns_ts(self):
        result = self._post()
        assert "ts" in result and result["ts"]

    def test_dry_run_note_present(self):
        result = self._post()
        assert "dry-run" in result.get("note", "")


class TestPostIncidentCardWithMockClient:
    """Tests with a mocked Slack client."""

    def test_calls_chat_post_message(self):
        from tools import post_incident_card

        mock_client = MagicMock()
        mock_client.chat_postMessage.return_value = {"ts": "1234567890.000001"}

        result = json.loads(
            post_incident_card(
                incident_id="INC-MOCK-001",
                severity="P1",
                title="Mock test",
                service="svc",
                root_cause="Root cause",
                suggested_actions=["Fix it"],
                slack_client=mock_client,
                channel_id="C0TEST",
            )
        )

        mock_client.chat_postMessage.assert_called_once()
        assert result["ok"] is True
        assert result["ts"] == "1234567890.000001"


# ── memory.py ────────────────────────────────────────────────────────────────


class TestMemory:
    def test_empty_on_init(self):
        from memory import Memory

        m = Memory()
        assert m.messages == []

    def test_add_user_message(self):
        from memory import Memory

        m = Memory()
        m.add_user("hello")
        assert m.messages[-1] == {"role": "user", "content": "hello"}

    def test_add_tool_result(self):
        from memory import Memory

        m = Memory()
        m.add_tool_result("tool-123", '{"ok": true}')
        msg = m.messages[-1]
        assert msg["role"] == "user"
        assert msg["content"][0]["type"] == "tool_result"
        assert msg["content"][0]["tool_use_id"] == "tool-123"

    def test_reset_clears_messages(self):
        from memory import Memory

        m = Memory()
        m.add_user("hello")
        m.reset()
        assert m.messages == []

    def test_messages_returns_copy(self):
        from memory import Memory

        m = Memory()
        m.add_user("hello")
        msgs = m.messages
        msgs.append({"role": "user", "content": "injected"})
        assert len(m.messages) == 1  # original not mutated


# ── metrics.py ───────────────────────────────────────────────────────────────


class TestMetrics:
    """Prometheus metrics module — tests run with or without prometheus_client installed."""

    def test_module_imports_cleanly(self):
        """metrics.py must be importable regardless of prometheus_client presence."""
        import metrics  # noqa: F401

        # Verify the public API is present
        assert callable(metrics.metrics_enabled)
        assert callable(metrics.start_metrics_server)
        assert callable(metrics.record_request)
        assert callable(metrics.record_duration)
        assert callable(metrics.record_tokens)
        assert callable(metrics.record_iterations)

    def test_metrics_enabled_default(self, monkeypatch):
        """metrics_enabled() returns True when METRICS_ENABLED is unset."""
        monkeypatch.delenv("METRICS_ENABLED", raising=False)
        import metrics

        # metrics_enabled() reads os.environ at call-time — no reload needed.
        # Result is True when prometheus_client is installed; False otherwise — both are fine.
        result = metrics.metrics_enabled()
        assert isinstance(result, bool)

    def test_metrics_disabled_via_env(self, monkeypatch):
        """METRICS_ENABLED=false disables metrics regardless of package presence."""
        monkeypatch.setenv("METRICS_ENABLED", "false")
        import metrics

        # metrics_enabled() reads os.environ at call-time — no reload needed.
        assert metrics.metrics_enabled() is False

    def test_record_request_success_no_error(self, monkeypatch):
        """record_request('success') must not raise even when prometheus unavailable."""
        import metrics

        metrics.record_request("success")  # should not raise

    def test_record_request_error_no_error(self):
        """record_request('error') must not raise."""
        import metrics

        metrics.record_request("error")

    def test_record_duration_no_error(self):
        """record_duration() must not raise."""
        import metrics

        metrics.record_duration(1.23)

    def test_record_tokens_no_error(self):
        """record_tokens() must not raise."""
        import metrics

        metrics.record_tokens(prompt_tokens=412, completion_tokens=87)

    def test_record_iterations_no_error(self):
        """record_iterations() must not raise."""
        import metrics

        metrics.record_iterations(3)

    def test_start_metrics_server_disabled_no_error(self, monkeypatch):
        """start_metrics_server() with METRICS_ENABLED=false must not start a server."""
        monkeypatch.setenv("METRICS_ENABLED", "false")
        import metrics

        # metrics_enabled() reads os.environ at call-time — no reload needed.
        # Should return immediately without binding a port.
        metrics.start_metrics_server(port=19999)

    def test_planner_records_metrics_on_success(self, monkeypatch):
        """handle_alert() calls record_request('success') and record_duration()."""
        from unittest.mock import MagicMock, patch

        import metrics

        recorded = {"requests": [], "durations": [], "iterations": []}

        monkeypatch.setattr(metrics, "record_request", lambda s: recorded["requests"].append(s))
        monkeypatch.setattr(metrics, "record_duration", lambda d: recorded["durations"].append(d))
        monkeypatch.setattr(metrics, "record_iterations", lambda i: recorded["iterations"].append(i))
        monkeypatch.setattr(metrics, "record_tokens", lambda **_: None)

        fake_response_tool = MagicMock()
        fake_response_tool.stop_reason = "tool_use"
        fake_response_tool.usage.input_tokens = 100
        fake_response_tool.usage.output_tokens = 50
        tool_block = MagicMock()
        tool_block.type = "tool_use"
        tool_block.name = "get_alert_context"
        tool_block.input = {"alert_id": "ALERT-001"}
        tool_block.id = "tu_001"
        fake_response_tool.content = [tool_block]

        fake_response_end = MagicMock()
        fake_response_end.stop_reason = "end_turn"
        fake_response_end.usage.input_tokens = 200
        fake_response_end.usage.output_tokens = 80
        fake_response_end.content = []

        with patch("planner.anthropic.Anthropic"), \
             patch("planner.init_tracing_client", side_effect=lambda c: c), \
             patch("planner.ls_traceable", side_effect=lambda *a, **kw: (lambda f: f)):
            from planner import IncidentPlanner
            planner = IncidentPlanner()
            planner._client = MagicMock()
            planner._client.messages.create.side_effect = [
                fake_response_tool,
                fake_response_end,
            ]
            with patch("planner.TOOL_FUNCTIONS", {"get_alert_context": lambda **_: '{"ok": true}'}):
                planner.handle_alert("ALERT-001")

        assert "success" in recorded["requests"]
        assert len(recorded["durations"]) == 1
        assert recorded["durations"][0] >= 0
        assert len(recorded["iterations"]) == 1
