"""
src/tools/docker_tool.py — Sandboxed test runner via Docker.

SAFETY CONTRACT
───────────────
  --network=none   No internet access. The fix cannot exfiltrate data
                   or pull malicious dependencies at test time.
  --read-only      Container filesystem is read-only (source is mounted).
  --rm             Container is deleted after tests finish.
  Non-root user    Defined in the target's Dockerfile (USER testrunner).

WHY DOCKER?
───────────
The agent generates code and runs it. Without a sandbox, a malicious or
buggy fix could delete files, open network connections, or escalate
privileges. Docker with --network=none is the minimum viable sandbox
for an auto-fix agent.

USAGE
─────
  result = run_tests_in_docker("/path/to/vulnerable_app")
  result.passed    → bool
  result.output    → combined stdout + stderr
  result.exit_code → int
"""

from __future__ import annotations

import logging
import subprocess
from dataclasses import dataclass
from pathlib import Path

log = logging.getLogger(__name__)

IMAGE_NAME = "sast-autofix-test-runner"
DEFAULT_TIMEOUT = 120  # seconds


@dataclass
class TestResult:
    passed: bool
    exit_code: int
    output: str


def build_image(target_dir: str) -> bool:
    """
    Build the Docker test-runner image from the target's Dockerfile.

    Returns True on success. Only needs to run once (or when Dockerfile changes).
    """
    target = Path(target_dir).resolve()
    dockerfile = target / "Dockerfile"

    if not dockerfile.exists():
        log.error("No Dockerfile found at %s", dockerfile)
        return False

    log.info("Building Docker image %s from %s", IMAGE_NAME, target)
    result = subprocess.run(
        ["docker", "build", "-t", IMAGE_NAME, str(target)],
        capture_output=True,
        text=True,
        timeout=300,
    )
    if result.returncode != 0:
        log.error("docker build failed:\n%s", result.stderr[-2000:])
        return False

    log.info("Docker image built: %s", IMAGE_NAME)
    return True


def run_tests_in_docker(target_dir: str, timeout: int = DEFAULT_TIMEOUT) -> TestResult:
    """
    Run the test suite inside a Docker container with --network=none.

    Mounts the target_dir as /app so the latest fixed files are used
    without rebuilding the image on every retry.

    Args:
        target_dir: Absolute path to the vulnerable_app directory.
        timeout:    Max seconds to wait for tests (default: 120).

    Returns:
        TestResult with passed, exit_code, and combined output.
    """
    target = Path(target_dir).resolve()

    # Ensure image exists
    check = subprocess.run(
        ["docker", "image", "inspect", IMAGE_NAME],
        capture_output=True,
    )
    if check.returncode != 0:
        log.info("Image not found — building...")
        if not build_image(target_dir):
            return TestResult(
                passed=False,
                exit_code=-1,
                output="[ERROR] Docker image build failed. Check Dockerfile.",
            )

    log.info("Running tests in Docker sandbox (network=none)...")

    cmd = [
        "docker", "run",
        "--rm",                              # delete container after run
        "--network=none",                    # no internet access
        "--read-only",                       # read-only container FS
        "--tmpfs", "/tmp",                   # allow writes to /tmp only
        "--volume", f"{target}:/app:ro",     # mount source read-only
        "--workdir", "/app",
        # Tell db.py to store SQLite in /tmp (writable tmpfs) rather than
        # the read-only /app mount.  db.py reads this at module-import time.
        "-e", "APP_DB_PATH=/tmp/app.db",
        IMAGE_NAME,
    ]

    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
        output = (result.stdout + result.stderr).strip()
        return TestResult(
            passed=result.returncode == 0,
            exit_code=result.returncode,
            output=output,
        )

    except subprocess.TimeoutExpired:
        return TestResult(
            passed=False,
            exit_code=-1,
            output=f"[ERROR] Tests timed out after {timeout}s",
        )
    except FileNotFoundError:
        return TestResult(
            passed=False,
            exit_code=-1,
            output="[ERROR] Docker not found — ensure Docker Desktop is running",
        )
