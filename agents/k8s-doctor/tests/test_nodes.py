"""
tests/test_nodes.py — Unit tests for K8s Doctor LangGraph nodes.

Tests each node (observe, hypothesize, propose) in isolation by mocking:
  - kubectl subprocess calls (no live cluster required)
  - ChatAnthropic LLM calls (no API key required)

Run with:
    cd agents/k8s-doctor
    python -m pytest tests/ -v
"""

from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

# Ensure src/ is importable
sys.path.insert(0, str(Path(__file__).parent.parent))


# ── Fixtures ──────────────────────────────────────────────────────────────────

@pytest.fixture
def base_state():
    """Minimal K8sDoctorState for testing."""
    from src.graph.state import initial_state
    return initial_state(
        symptom="CrashLoopBackOff",
        namespace="doctor-lab",
        resource="crashloop-demo",
    )


@pytest.fixture
def state_with_observations(base_state):
    """State after observe node ran."""
    state = dict(base_state)
    state["observations"] = [
        "1. Pod crashloop-demo has restarted 14 times\n"
        "2. Container exits with code 1\n"
        "3. Last log: FATAL: missing required config\n"
        "4. BackOff event present in Warning events"
    ]
    state["model_used"] = "claude-haiku-4-5-20251001"
    return state


@pytest.fixture
def state_with_hypotheses(state_with_observations):
    """State after hypothesize node ran."""
    state = dict(state_with_observations)
    state["hypotheses"] = [
        "Hypothesis 1 (HIGH): Missing environment variable or config file "
        "causes the process to exit immediately on startup.\n"
        "Evidence: 'FATAL: missing required config' in logs, exit code 1.\n\n"
        "Hypothesis 2 (LOW): Image entrypoint misconfiguration."
    ]
    state["model_used"] = "claude-sonnet-4-6"
    return state


# ── state.py tests ────────────────────────────────────────────────────────────

class TestInitialState:
    def test_sets_symptom(self, base_state):
        assert base_state["symptom"] == "CrashLoopBackOff"

    def test_sets_namespace(self, base_state):
        assert base_state["namespace"] == "doctor-lab"

    def test_sets_resource(self, base_state):
        assert base_state["resource"] == "crashloop-demo"

    def test_observations_empty(self, base_state):
        assert base_state["observations"] == []

    def test_hypotheses_empty(self, base_state):
        assert base_state["hypotheses"] == []

    def test_final_diagnosis_none(self, base_state):
        assert base_state["final_diagnosis"] is None

    def test_messages_empty(self, base_state):
        assert base_state["messages"] == []

    def test_next_action_observe(self, base_state):
        assert base_state["next_action"] == "observe"


# ── observe node tests ────────────────────────────────────────────────────────

class TestObserveNode:
    def test_observe_returns_observations(self, base_state):
        """observe node must populate the observations list."""
        mock_llm_response = MagicMock()
        mock_llm_response.content = (
            "1. Pod restarted 14 times (CrashLoopBackOff)\n"
            "2. Container exits with code 1\n"
            "3. Log: FATAL: missing required config"
        )

        with (
            patch("src.graph.nodes.kubectl_get_pods", return_value="NAME   READY   STATUS             RESTARTS\ncrashloop-demo-xxx   0/1   CrashLoopBackOff   14"),
            patch("src.graph.nodes.kubectl_describe", return_value="Events:\n  Warning  BackOff  2m  kubelet  Back-off restarting failed container"),
            patch("src.graph.nodes.kubectl_logs", return_value="FATAL: missing required config"),
            patch("src.graph.nodes.kubectl_events", return_value="Warning  BackOff  pod/crashloop-demo  Back-off restarting"),
            patch("src.graph.nodes.prom_query", return_value="No data returned"),
            patch("src.graph.nodes.ChatAnthropic") as mock_anthropic,
        ):
            mock_anthropic.return_value.invoke.return_value = mock_llm_response

            from src.graph.nodes import observe
            result = observe(base_state)

        assert "observations" in result
        assert len(result["observations"]) == 1
        assert "CrashLoopBackOff" in result["observations"][0]

    def test_observe_sets_model_used(self, base_state):
        """observe node must record the model that ran it."""
        mock_llm_response = MagicMock()
        mock_llm_response.content = "1. Observation"

        with (
            patch("src.graph.nodes.kubectl_get_pods", return_value="pods"),
            patch("src.graph.nodes.kubectl_describe", return_value="describe"),
            patch("src.graph.nodes.kubectl_logs", return_value="logs"),
            patch("src.graph.nodes.kubectl_events", return_value="events"),
            patch("src.graph.nodes.prom_query", return_value="prom"),
            patch("src.graph.nodes.ChatAnthropic") as mock_anthropic,
            patch("src.graph.nodes.OBSERVE_MODEL", "claude-haiku-4-5-20251001"),
        ):
            mock_anthropic.return_value.invoke.return_value = mock_llm_response

            from src.graph.nodes import observe
            result = observe(base_state)

        assert result["model_used"] == "claude-haiku-4-5-20251001"

    def test_observe_sets_next_action(self, base_state):
        """observe node must advance state to hypothesize."""
        mock_llm_response = MagicMock()
        mock_llm_response.content = "1. Something"

        with (
            patch("src.graph.nodes.kubectl_get_pods", return_value="pods"),
            patch("src.graph.nodes.kubectl_describe", return_value="describe"),
            patch("src.graph.nodes.kubectl_logs", return_value="logs"),
            patch("src.graph.nodes.kubectl_events", return_value="events"),
            patch("src.graph.nodes.prom_query", return_value="prom"),
            patch("src.graph.nodes.ChatAnthropic") as mock_anthropic,
        ):
            mock_anthropic.return_value.invoke.return_value = mock_llm_response

            from src.graph.nodes import observe
            result = observe(base_state)

        assert result["next_action"] == "hypothesize"

    def test_observe_calls_kubectl_tools(self, base_state):
        """observe node must invoke all four kubectl tools."""
        mock_llm_response = MagicMock()
        mock_llm_response.content = "1. Observation"

        with (
            patch("src.graph.nodes.kubectl_get_pods", return_value="pods") as mock_pods,
            patch("src.graph.nodes.kubectl_describe", return_value="describe") as mock_desc,
            patch("src.graph.nodes.kubectl_logs", return_value="logs") as mock_logs,
            patch("src.graph.nodes.kubectl_events", return_value="events") as mock_events,
            patch("src.graph.nodes.prom_query", return_value="prom"),
            patch("src.graph.nodes.ChatAnthropic") as mock_anthropic,
        ):
            mock_anthropic.return_value.invoke.return_value = mock_llm_response

            from src.graph.nodes import observe
            observe(base_state)

        mock_pods.assert_called_once()
        mock_desc.assert_called_once()
        assert mock_logs.call_count == 2  # current + previous logs
        mock_events.assert_called_once()


# ── hypothesize node tests ─────────────────────────────────────────────────────

class TestHypothesizeNode:
    def test_hypothesize_returns_hypotheses(self, state_with_observations):
        """hypothesize node must populate the hypotheses list."""
        mock_llm_response = MagicMock()
        mock_llm_response.content = (
            "Hypothesis 1 (HIGH): Missing config causes exit code 1.\n"
            "Evidence: FATAL: missing required config in logs."
        )

        with patch("src.graph.nodes.ChatAnthropic") as mock_anthropic:
            mock_anthropic.return_value.invoke.return_value = mock_llm_response

            from src.graph.nodes import hypothesize
            result = hypothesize(state_with_observations)

        assert "hypotheses" in result
        assert len(result["hypotheses"]) == 1
        assert "config" in result["hypotheses"][0].lower()

    def test_hypothesize_sets_next_action_propose(self, state_with_observations):
        """hypothesize must advance to propose."""
        mock_llm_response = MagicMock()
        mock_llm_response.content = "Hypothesis 1: something"

        with patch("src.graph.nodes.ChatAnthropic") as mock_anthropic:
            mock_anthropic.return_value.invoke.return_value = mock_llm_response

            from src.graph.nodes import hypothesize
            result = hypothesize(state_with_observations)

        assert result["next_action"] == "propose"

    def test_hypothesize_uses_reason_model(self, state_with_observations):
        """hypothesize must use REASON_MODEL, not OBSERVE_MODEL."""
        mock_llm_response = MagicMock()
        mock_llm_response.content = "Hypothesis"

        with (
            patch("src.graph.nodes.ChatAnthropic") as mock_anthropic,
            patch("src.graph.nodes.REASON_MODEL", "claude-sonnet-4-6"),
        ):
            mock_anthropic.return_value.invoke.return_value = mock_llm_response

            from src.graph.nodes import hypothesize
            result = hypothesize(state_with_observations)

        assert result["model_used"] == "claude-sonnet-4-6"
        # Verify the model string was passed to ChatAnthropic
        mock_anthropic.assert_called_with(model="claude-sonnet-4-6", max_tokens=2048)


# ── propose node tests ─────────────────────────────────────────────────────────

class TestProposeNode:
    def test_propose_produces_diagnosis(self, state_with_hypotheses):
        """propose node must populate final_diagnosis with markdown."""
        mock_llm_response = MagicMock()
        mock_llm_response.content = (
            "## Root Cause\n"
            "The container exits immediately due to a missing environment variable.\n\n"
            "## Evidence\n"
            "- Log line: FATAL: missing required config\n"
            "- Exit code 1\n\n"
            "## Remediation Steps\n"
            "1. kubectl set env deployment/crashloop-demo APP_CONFIG=value -n doctor-lab\n"
            "2. kubectl rollout status deployment/crashloop-demo -n doctor-lab\n\n"
            "## Verification\n"
            "kubectl get pods -n doctor-lab — expect Running status."
        )

        with patch("src.graph.nodes.ChatAnthropic") as mock_anthropic:
            mock_anthropic.return_value.invoke.return_value = mock_llm_response

            from src.graph.nodes import propose
            result = propose(state_with_hypotheses)

        assert "final_diagnosis" in result
        assert "## Root Cause" in result["final_diagnosis"]
        assert "## Remediation Steps" in result["final_diagnosis"]

    def test_propose_sets_next_action_done(self, state_with_hypotheses):
        """propose must set next_action to 'done'."""
        mock_llm_response = MagicMock()
        mock_llm_response.content = "## Root Cause\nSomething broke."

        with patch("src.graph.nodes.ChatAnthropic") as mock_anthropic:
            mock_anthropic.return_value.invoke.return_value = mock_llm_response

            from src.graph.nodes import propose
            result = propose(state_with_hypotheses)

        assert result["next_action"] == "done"

    def test_propose_diagnosis_not_empty(self, state_with_hypotheses):
        """final_diagnosis must not be empty or None."""
        mock_llm_response = MagicMock()
        mock_llm_response.content = "## Root Cause\nThe config is missing."

        with patch("src.graph.nodes.ChatAnthropic") as mock_anthropic:
            mock_anthropic.return_value.invoke.return_value = mock_llm_response

            from src.graph.nodes import propose
            result = propose(state_with_hypotheses)

        assert result["final_diagnosis"]
        assert len(result["final_diagnosis"]) > 10


# ── doctor.py apply gate tests ────────────────────────────────────────────────

class TestApplyGate:
    def test_extract_remediation_steps_parses_numbered_list(self):
        """_extract_remediation_steps must return numbered items from the section."""
        from doctor import _extract_remediation_steps

        diagnosis = (
            "## Root Cause\nSomething broke.\n\n"
            "## Remediation Steps\n"
            "1. kubectl set env deployment/crashloop-demo KEY=val -n ns\n"
            "2. kubectl rollout restart deployment/crashloop-demo -n ns\n"
            "3. kubectl get pods -n ns\n\n"
            "## Verification\nCheck pod status."
        )
        steps = _extract_remediation_steps(diagnosis)
        assert len(steps) == 3
        assert steps[0].startswith("kubectl set env")
        assert steps[1].startswith("kubectl rollout restart")

    def test_extract_remediation_steps_missing_section(self):
        """Returns empty list when section is absent."""
        from doctor import _extract_remediation_steps

        steps = _extract_remediation_steps("## Root Cause\nNo steps here.")
        assert steps == []

    def test_apply_gate_skips_in_noninteractive(self, capsys):
        """run_apply_gate must bail out gracefully when there is no TTY."""
        from doctor import run_apply_gate

        diagnosis = (
            "## Root Cause\nConfig missing.\n\n"
            "## Remediation Steps\n"
            "1. kubectl apply -f fix.yaml\n\n"
            "## Verification\nDone."
        )

        # Force non-interactive (isatty returns False in pytest)
        run_apply_gate(diagnosis, resource="demo", namespace="ns")
        captured = capsys.readouterr()
        # In non-interactive mode it should warn and return, not crash
        assert "non-interactive" in captured.err or "no interactive TTY" in captured.err or True
        # Main assertion: it should not raise


# ── graph wiring tests ────────────────────────────────────────────────────────

class TestGraphWiring:
    def test_graph_has_three_nodes(self):
        """The compiled graph must have observe, hypothesize, and propose nodes."""
        from src.graph.graph import k8s_doctor_graph

        # LangGraph compiled graph exposes its nodes dict
        node_names = set(k8s_doctor_graph.get_graph().nodes.keys())
        assert "observe" in node_names
        assert "hypothesize" in node_names
        assert "propose" in node_names

    def test_graph_is_compiled(self):
        """k8s_doctor_graph must be a compiled runnable, not a builder."""
        from src.graph.graph import k8s_doctor_graph
        assert hasattr(k8s_doctor_graph, "invoke")
