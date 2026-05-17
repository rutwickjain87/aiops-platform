"""
tests/test_tools.py — Unit tests for K8s Doctor kubectl and Prometheus tools.

Tests the tool wrappers without running actual kubectl or Prometheus —
all subprocess and HTTP calls are mocked.

Run with:
    cd agents/k8s-doctor
    python -m pytest tests/ -v
"""

from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))


# ── kubectl tool tests ────────────────────────────────────────────────────────

class TestKubectlDescribe:
    def test_returns_stdout_on_success(self):
        from src.tools.kubectl import kubectl_describe

        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = "Name: crashloop-demo\nNamespace: doctor-lab"
        mock_result.stderr = ""

        with patch("subprocess.run", return_value=mock_result):
            output = kubectl_describe("crashloop-demo", "doctor-lab")

        assert "crashloop-demo" in output
        assert "doctor-lab" in output

    def test_returns_error_on_nonzero_exit(self):
        from src.tools.kubectl import kubectl_describe

        mock_result = MagicMock()
        mock_result.returncode = 1
        mock_result.stdout = ""
        mock_result.stderr = 'Error from server (NotFound): deployments.apps "crashloop-demo" not found'

        with patch("subprocess.run", return_value=mock_result):
            output = kubectl_describe("crashloop-demo", "doctor-lab")

        assert "[kubectl exit 1]" in output
        assert "NotFound" in output

    def test_handles_kubectl_not_found(self):
        from src.tools.kubectl import kubectl_describe

        with patch("subprocess.run", side_effect=FileNotFoundError()):
            output = kubectl_describe("crashloop-demo", "doctor-lab")

        assert "kubectl not found" in output

    def test_handles_timeout(self):
        import subprocess
        from src.tools.kubectl import kubectl_describe

        with patch("subprocess.run", side_effect=subprocess.TimeoutExpired("kubectl", 15)):
            output = kubectl_describe("crashloop-demo", "doctor-lab")

        assert "timed out" in output


class TestKubectlLogs:
    def test_returns_log_lines(self):
        from src.tools.kubectl import kubectl_logs

        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = "FATAL: missing required config"
        mock_result.stderr = ""

        with patch("subprocess.run", return_value=mock_result):
            output = kubectl_logs("crashloop-demo", "doctor-lab")

        assert "FATAL" in output

    def test_previous_flag_appended(self):
        """previous=True must add --previous to the command."""
        from src.tools.kubectl import kubectl_logs

        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = "last crash log"
        mock_result.stderr = ""

        with patch("subprocess.run", return_value=mock_result) as mock_run:
            kubectl_logs("crashloop-demo", "doctor-lab", previous=True)

        cmd = mock_run.call_args[0][0]
        assert "--previous" in cmd

    def test_no_previous_flag_by_default(self):
        from src.tools.kubectl import kubectl_logs

        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = "current log"
        mock_result.stderr = ""

        with patch("subprocess.run", return_value=mock_result) as mock_run:
            kubectl_logs("crashloop-demo", "doctor-lab")

        cmd = mock_run.call_args[0][0]
        assert "--previous" not in cmd


class TestKubectlEvents:
    def test_returns_warning_events(self):
        from src.tools.kubectl import kubectl_events

        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = "Warning  BackOff  pod/crashloop-demo  Back-off restarting"
        mock_result.stderr = ""

        with patch("subprocess.run", return_value=mock_result):
            output = kubectl_events("doctor-lab")

        assert "BackOff" in output

    def test_includes_field_selector(self):
        """events command must filter by type=Warning by default."""
        from src.tools.kubectl import kubectl_events

        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = "events"
        mock_result.stderr = ""

        with patch("subprocess.run", return_value=mock_result) as mock_run:
            kubectl_events("doctor-lab")

        cmd = mock_run.call_args[0][0]
        assert any("type=Warning" in arg for arg in cmd)


class TestKubectlGetPods:
    def test_returns_pod_list(self):
        from src.tools.kubectl import kubectl_get_pods

        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = (
            "NAME                             READY   STATUS             RESTARTS   AGE\n"
            "crashloop-demo-7d9f8b6c5-xk2qp   0/1     CrashLoopBackOff   14         22m"
        )
        mock_result.stderr = ""

        with patch("subprocess.run", return_value=mock_result):
            output = kubectl_get_pods("doctor-lab")

        assert "CrashLoopBackOff" in output
        assert "RESTARTS" in output


# ── Prometheus tool tests ─────────────────────────────────────────────────────

class TestPromQuery:
    def test_returns_metric_value(self):
        from src.tools.prometheus import prom_query

        mock_response = MagicMock()
        mock_response.json.return_value = {
            "status": "success",
            "data": {
                "resultType": "vector",
                "result": [
                    {
                        "metric": {"job": "kubernetes-pods", "instance": "10.0.0.1:8080"},
                        "value": [1620000000, "1"],
                    }
                ],
            },
        }
        mock_response.raise_for_status = MagicMock()

        with patch("requests.get", return_value=mock_response):
            output = prom_query("up")

        assert "up" in output
        assert "1" in output

    def test_returns_no_data_message(self):
        from src.tools.prometheus import prom_query

        mock_response = MagicMock()
        mock_response.json.return_value = {
            "status": "success",
            "data": {"resultType": "vector", "result": []},
        }
        mock_response.raise_for_status = MagicMock()

        with patch("requests.get", return_value=mock_response):
            output = prom_query("nonexistent_metric")

        assert "No data" in output

    def test_handles_connection_error(self):
        import requests as req
        from src.tools.prometheus import prom_query

        with patch("requests.get", side_effect=req.exceptions.ConnectionError()):
            output = prom_query("up")

        assert "Cannot connect" in output
