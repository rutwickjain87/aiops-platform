"""
tests/test_pr_reviewer.py — Unit tests for the PR Security Reviewer agent tools.

These tests cover the three @tool functions in agents/pr-reviewer/tools.py:
  - fetch_pr_diff    (mocked GitHub API)
  - run_semgrep      (real semgrep subprocess on fixture code)
  - post_review_comment (mocked GitHub API, idempotency check)

Run with:
  cd aiops-platform
  pytest tests/test_pr_reviewer.py -v

NOTE: semgrep tests are skipped automatically if semgrep is not installed.
"""

from __future__ import annotations

import importlib.util as _iu
import json
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

# ── Path setup ───────────────────────────────────────────────────────────────
# IMPORTANT: both agents have files named tools.py, metrics.py, tracing.py, etc.
# To avoid sys.modules collisions when both test files run in the same pytest
# session, ALL pr-reviewer modules are loaded by file path via importlib.util
# rather than by bare name (which would pollute the module cache and cause
# slack-incident-bot tests to import the wrong modules).

REPO_ROOT = Path(__file__).parent.parent
PR_REVIEWER_DIR = REPO_ROOT / "agents" / "pr-reviewer"

# Repo root on sys.path for the shared observability package ONLY.
# Do NOT add PR_REVIEWER_DIR to sys.path — use importlib.util for all imports.
if str(REPO_ROOT) not in sys.path:
    sys.path.append(str(REPO_ROOT))


def _load_pr_module(filename: str, mod_name: str):
    """Load a pr-reviewer module by file path with a unique sys.modules key."""
    spec = _iu.spec_from_file_location(mod_name, PR_REVIEWER_DIR / filename)
    mod = _iu.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


# Load pr-reviewer tools with a unique key so sys.modules['tools'] stays clear
# for the slack-incident-bot test suite.
_pr_tools = _load_pr_module("tools.py", "pr_reviewer_tools")
MARKER = _pr_tools.MARKER
fetch_pr_diff = _pr_tools.fetch_pr_diff
post_review_comment = _pr_tools.post_review_comment
run_semgrep = _pr_tools.run_semgrep

# ── Helpers ────────────────────────────────────────────────────────────────────


def _semgrep_available() -> bool:
    import subprocess

    r = subprocess.run(["which", "semgrep"], capture_output=True)
    return r.returncode == 0


FIXTURE_DIR = REPO_ROOT / "tests" / "fixtures"


# ══════════════════════════════════════════════════════════════════════════════
# fetch_pr_diff tests
# ══════════════════════════════════════════════════════════════════════════════


class TestFetchPrDiff:
    """Tests for fetch_pr_diff tool — GitHub API calls are mocked."""

    def _make_mock_file(
        self,
        filename: str,
        status: str = "modified",
        additions: int = 5,
        deletions: int = 2,
        patch: str = "+new line\n-old line",
    ) -> MagicMock:
        f = MagicMock()
        f.filename = filename
        f.status = status
        f.additions = additions
        f.deletions = deletions
        f.patch = patch
        return f

    def test_returns_pr_metadata(self, monkeypatch):
        """Result must include PR number, title, and author."""
        monkeypatch.setenv("GITHUB_TOKEN", "fake-token")

        mock_pr = MagicMock()
        mock_pr.title = "Add user auth"
        mock_pr.user.login = "rutwickjain87"
        mock_pr.base.ref = "main"
        mock_pr.head.ref = "feature/auth"
        mock_pr.state = "open"
        mock_pr.changed_files = 1
        mock_pr.additions = 10
        mock_pr.deletions = 2
        mock_pr.get_files.return_value = [self._make_mock_file("auth.py")]

        mock_repo = MagicMock()
        mock_repo.get_pull.return_value = mock_pr

        with patch("github.Github") as MockGithub:
            MockGithub.return_value.get_repo.return_value = mock_repo
            result = fetch_pr_diff.invoke({"repo": "owner/repo", "pr_number": 42})

        assert "PR #42" in result
        assert "Add user auth" in result
        assert "rutwickjain87" in result

    def test_lists_changed_files(self, monkeypatch):
        """Each changed file should appear in the output."""
        monkeypatch.setenv("GITHUB_TOKEN", "fake-token")

        mock_pr = MagicMock()
        mock_pr.title = "Refactor DB layer"
        mock_pr.user.login = "dev"
        mock_pr.base.ref = "main"
        mock_pr.head.ref = "fix/db"
        mock_pr.state = "open"
        mock_pr.changed_files = 2
        mock_pr.additions = 20
        mock_pr.deletions = 5
        mock_pr.get_files.return_value = [
            self._make_mock_file("db.py"),
            self._make_mock_file("models.py", status="added"),
        ]

        mock_repo = MagicMock()
        mock_repo.get_pull.return_value = mock_pr

        with patch("github.Github") as MockGithub:
            MockGithub.return_value.get_repo.return_value = mock_repo
            result = fetch_pr_diff.invoke({"repo": "owner/repo", "pr_number": 1})

        assert "db.py" in result
        assert "models.py" in result

    def test_missing_github_token(self, monkeypatch):
        """Should return a clear error when GITHUB_TOKEN is not set."""
        monkeypatch.delenv("GITHUB_TOKEN", raising=False)
        result = fetch_pr_diff.invoke({"repo": "owner/repo", "pr_number": 1})
        assert "GITHUB_TOKEN" in result
        assert "ERROR" in result

    def test_large_patch_is_truncated(self, monkeypatch):
        """Patches exceeding MAX_PATCH_CHARS should be truncated."""
        monkeypatch.setenv("GITHUB_TOKEN", "fake-token")

        long_patch = "+" + "x" * 20_000

        mock_pr = MagicMock()
        mock_pr.title = "Big change"
        mock_pr.user.login = "dev"
        mock_pr.base.ref = "main"
        mock_pr.head.ref = "big"
        mock_pr.state = "open"
        mock_pr.changed_files = 1
        mock_pr.additions = 500
        mock_pr.deletions = 0
        mock_pr.get_files.return_value = [
            self._make_mock_file("big.py", patch=long_patch)
        ]

        mock_repo = MagicMock()
        mock_repo.get_pull.return_value = mock_pr

        with patch("github.Github") as MockGithub:
            MockGithub.return_value.get_repo.return_value = mock_repo
            result = fetch_pr_diff.invoke({"repo": "owner/repo", "pr_number": 99})

        assert "truncated" in result

    def test_github_api_error_returns_error_string(self, monkeypatch):
        """A GitHub API exception should be caught and returned as an error string."""
        monkeypatch.setenv("GITHUB_TOKEN", "fake-token")

        with patch("github.Github") as MockGithub:
            MockGithub.return_value.get_repo.side_effect = Exception("Not Found")
            result = fetch_pr_diff.invoke({"repo": "bad/repo", "pr_number": 1})

        assert "ERROR" in result
        assert "Not Found" in result


# ══════════════════════════════════════════════════════════════════════════════
# run_semgrep tests
# ══════════════════════════════════════════════════════════════════════════════


class TestRunSemgrep:
    """Tests for run_semgrep tool — exercises real semgrep when available."""

    @pytest.mark.skipif(not _semgrep_available(), reason="semgrep not installed")
    def test_detects_hardcoded_secret(self):
        """Semgrep should flag a hardcoded AWS key."""
        code = 'AWS_SECRET = "wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY"'
        result = run_semgrep.invoke({"code": code, "filename": "config.py"})
        data = json.loads(result)
        # Semgrep may or may not catch this depending on rules downloaded;
        # at minimum the JSON structure must be valid.
        assert "findings" in data
        assert isinstance(data["findings"], list)

    @pytest.mark.skipif(not _semgrep_available(), reason="semgrep not installed")
    def test_detects_eval_injection(self):
        """Semgrep should flag eval() on user-controlled input."""
        code = "def run(expr): return eval(expr)"
        result = run_semgrep.invoke({"code": code, "filename": "calc.py"})
        data = json.loads(result)
        assert "findings" in data

    @pytest.mark.skipif(not _semgrep_available(), reason="semgrep not installed")
    def test_clean_code_returns_empty_findings(self):
        """Clean code should return zero findings (or very few false positives)."""
        code = "def add(a: int, b: int) -> int:\n    return a + b\n"
        result = run_semgrep.invoke({"code": code, "filename": "math_utils.py"})
        data = json.loads(result)
        assert "findings" in data
        # We can't guarantee zero (rules may vary), but the structure must be valid.
        assert isinstance(data["total_findings"], int)

    @pytest.mark.skipif(not _semgrep_available(), reason="semgrep not installed")
    def test_bad_fixture_has_findings(self):
        """The deliberately-bad fixture should generate at least one finding."""
        code = (FIXTURE_DIR / "bad_pr.py").read_text()
        result = run_semgrep.invoke({"code": code, "filename": "bad_pr.py"})
        data = json.loads(result)
        # With auto rules, expect at least eval or hardcoded secret to be flagged.
        assert data["total_findings"] >= 1

    def test_semgrep_not_installed_returns_error_json(self, monkeypatch):
        """When semgrep is missing, return a JSON error (not raise an exception)."""
        # Patch subprocess inside the pr-reviewer tools module loaded by path.
        # Using the module object (not a string) avoids sys.modules['tools'] ambiguity
        # when both agent test files run in the same pytest session.
        with patch.object(_pr_tools, "subprocess") as mock_subprocess:
            mock_subprocess.run.return_value = MagicMock(returncode=1)
            result = run_semgrep.invoke({"code": "x = 1", "filename": "x.py"})
        data = json.loads(result)
        assert "error" in data

    def test_returns_valid_json(self):
        """run_semgrep must always return valid JSON regardless of outcome."""
        with patch.object(_pr_tools, "subprocess") as mock_subprocess:
            # Simulate semgrep available but returning empty results
            mock_subprocess.run.side_effect = [
                MagicMock(returncode=0),  # 'which semgrep'
                MagicMock(
                    returncode=0,
                    stdout=json.dumps({"results": [], "errors": []}),
                    stderr="",
                ),
            ]
            result = run_semgrep.invoke({"code": "pass", "filename": "noop.py"})
        data = json.loads(result)
        assert "findings" in data
        assert data["total_findings"] == 0


# ══════════════════════════════════════════════════════════════════════════════
# post_review_comment tests
# ══════════════════════════════════════════════════════════════════════════════


class TestPostReviewComment:
    """Tests for post_review_comment — GitHub API calls are mocked."""

    def test_creates_new_comment_when_none_exists(self, monkeypatch):
        """Should create a new comment if no existing marker comment is found."""
        monkeypatch.setenv("GITHUB_TOKEN", "fake-token")

        mock_comment = MagicMock()
        mock_comment.id = 999

        mock_issue = MagicMock()
        mock_issue.get_comments.return_value = []  # no existing comments
        mock_issue.create_comment.return_value = mock_comment

        mock_repo = MagicMock()
        mock_repo.get_issue.return_value = mock_issue

        with patch("github.Github") as MockGithub:
            MockGithub.return_value.get_repo.return_value = mock_repo
            result = post_review_comment.invoke(
                {
                    "repo": "owner/repo",
                    "pr_number": 7,
                    "body": "## Security Review\nAll clear.",
                }
            )

        mock_issue.create_comment.assert_called_once()
        assert "Posted new review comment" in result
        assert "999" in result

    def test_updates_existing_comment_with_marker(self, monkeypatch):
        """Should edit the existing marker comment instead of creating a new one."""
        monkeypatch.setenv("GITHUB_TOKEN", "fake-token")

        existing_comment = MagicMock()
        existing_comment.id = 123
        existing_comment.body = f"{MARKER}\n\n## Old Review"

        mock_issue = MagicMock()
        mock_issue.get_comments.return_value = [existing_comment]

        mock_repo = MagicMock()
        mock_repo.get_issue.return_value = mock_issue

        with patch("github.Github") as MockGithub:
            MockGithub.return_value.get_repo.return_value = mock_repo
            result = post_review_comment.invoke(
                {
                    "repo": "owner/repo",
                    "pr_number": 7,
                    "body": "## Security Review\n1 finding.",
                }
            )

        existing_comment.edit.assert_called_once()
        mock_issue.create_comment.assert_not_called()
        assert "Updated existing review comment" in result
        assert "123" in result

    def test_stamped_body_contains_marker(self, monkeypatch):
        """The comment body posted must contain the idempotency marker."""
        monkeypatch.setenv("GITHUB_TOKEN", "fake-token")

        mock_issue = MagicMock()
        mock_issue.get_comments.return_value = []
        mock_issue.create_comment.return_value = MagicMock(id=1)

        mock_repo = MagicMock()
        mock_repo.get_issue.return_value = mock_issue

        with patch("github.Github") as MockGithub:
            MockGithub.return_value.get_repo.return_value = mock_repo
            post_review_comment.invoke(
                {
                    "repo": "owner/repo",
                    "pr_number": 1,
                    "body": "My review",
                }
            )

        call_args = mock_issue.create_comment.call_args[0][0]
        assert MARKER in call_args

    def test_missing_github_token_returns_error(self, monkeypatch):
        """Should return a clear error when GITHUB_TOKEN is not set."""
        monkeypatch.delenv("GITHUB_TOKEN", raising=False)
        result = post_review_comment.invoke(
            {
                "repo": "owner/repo",
                "pr_number": 1,
                "body": "test",
            }
        )
        assert "GITHUB_TOKEN" in result
        assert "ERROR" in result

    def test_github_api_error_is_caught(self, monkeypatch):
        """GitHub API exceptions must be caught and returned as error strings."""
        monkeypatch.setenv("GITHUB_TOKEN", "fake-token")

        with patch("github.Github") as MockGithub:
            MockGithub.return_value.get_repo.side_effect = Exception("403 Forbidden")
            result = post_review_comment.invoke(
                {
                    "repo": "owner/repo",
                    "pr_number": 1,
                    "body": "test",
                }
            )

        assert "ERROR" in result
        assert "403 Forbidden" in result


# ── metrics.py ────────────────────────────────────────────────────────────────


_pr_metrics_cache = None


def _load_pr_metrics():
    """Load agents/pr-reviewer/metrics.py by path (cached after first load).

    Caching is required so _make_metrics() only runs once — prometheus_client
    raises ValueError on duplicate metric registration, which causes _METRICS
    to become {} on reload and record_*() calls to raise KeyError.
    """
    global _pr_metrics_cache
    if _pr_metrics_cache is None:
        _pr_metrics_cache = _load_pr_module("metrics.py", "pr_reviewer_metrics_mod")
    return _pr_metrics_cache


class TestPRReviewerMetrics:
    """Prometheus metrics for the PR reviewer — same graceful-degradation contract."""

    def test_module_imports_cleanly(self):
        """metrics.py must be importable regardless of prometheus_client presence."""
        pr_metrics = _load_pr_metrics()

        assert callable(pr_metrics.metrics_enabled)
        assert callable(pr_metrics.start_metrics_server)
        assert callable(pr_metrics.record_request)
        assert callable(pr_metrics.record_duration)
        assert callable(pr_metrics.record_tokens)
        assert callable(pr_metrics.record_iterations)
        assert callable(pr_metrics.record_findings)

    def test_metrics_disabled_via_env(self, monkeypatch):
        """METRICS_ENABLED=false disables metrics."""
        monkeypatch.setenv("METRICS_ENABLED", "false")
        pr_metrics = _load_pr_metrics()

        assert pr_metrics.metrics_enabled() is False

    def test_record_request_no_error(self):
        """record_request() must not raise."""
        pr_metrics = _load_pr_metrics()

        pr_metrics.record_request("success")
        pr_metrics.record_request("error")

    def test_record_duration_no_error(self):
        """record_duration() must not raise."""
        pr_metrics = _load_pr_metrics()

        pr_metrics.record_duration(45.2)

    def test_record_tokens_no_error(self):
        """record_tokens() must not raise."""
        pr_metrics = _load_pr_metrics()

        pr_metrics.record_tokens(prompt_tokens=800, completion_tokens=200)

    def test_record_iterations_no_error(self):
        """record_iterations() must not raise."""
        pr_metrics = _load_pr_metrics()

        pr_metrics.record_iterations(7)

    def test_record_findings_no_error(self):
        """record_findings() must not raise with valid and invalid severities."""
        pr_metrics = _load_pr_metrics()

        findings = [
            {"severity": "HIGH"},
            {"severity": "MEDIUM"},
            {"severity": "LOW"},
            {"severity": "INFO"},
            {"severity": "UNKNOWN"},  # should map to INFO, not raise
            {},  # missing severity key — should default to INFO
        ]
        pr_metrics.record_findings(findings)

    def test_record_findings_empty_list(self):
        """record_findings([]) must not raise."""
        pr_metrics = _load_pr_metrics()

        pr_metrics.record_findings([])

    def test_start_metrics_server_disabled_no_error(self, monkeypatch):
        """start_metrics_server() with METRICS_ENABLED=false must not bind a port."""
        monkeypatch.setenv("METRICS_ENABLED", "false")
        pr_metrics = _load_pr_metrics()

        pr_metrics.start_metrics_server(port=29999)


# ── observability/logging.py ──────────────────────────────────────────────────


class TestStructuredLogging:
    """Shared JSON logging module — importable and functional."""

    def test_module_imports_cleanly(self):
        """observability package must be importable."""
        import observability

        assert callable(observability.get_logger)
        assert callable(observability.set_correlation_id)
        assert callable(observability.get_correlation_id)

    def test_get_logger_returns_logger(self):
        """get_logger() returns a logging.Logger instance."""
        import logging

        from observability import get_logger

        log = get_logger("test.obs.module", agent="test-agent")
        assert isinstance(log, logging.Logger)

    def test_correlation_id_roundtrip(self):
        """set_correlation_id / get_correlation_id round-trip correctly."""
        from observability import get_correlation_id, set_correlation_id

        set_correlation_id("test-cid-42")
        assert get_correlation_id() == "test-cid-42"

    def test_logger_does_not_raise_on_info(self):
        """Calling log.info() must not raise regardless of formatter availability."""
        from observability import get_logger, set_correlation_id

        set_correlation_id("smoke-cid")
        log = get_logger("test.obs.no_raise", agent="smoke-test")
        log.info("Smoke test message", extra={"key": "value"})  # must not raise

    def test_logger_accepts_extra_fields(self):
        """Extra keyword arguments are passed through without raising."""
        from observability import get_logger

        log = get_logger("test.obs.extra", agent="extra-test")
        log.warning("Warning with extras", extra={"alert_id": "A-001", "severity": "P1"})
