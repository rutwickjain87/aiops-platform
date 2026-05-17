"""
src/tools/terraform_tool.py — Terraform validation tooling.

VALIDATION STRATEGY
───────────────────
Runs `terraform init -backend=false` then `terraform validate` against
the generated .tf files. Two modes, tried in order:

  1. Local terraform binary  — fastest; used if `terraform` is in PATH.
  2. Docker (hashicorp/terraform:latest) — used as fallback; needs Docker running.

`terraform init -backend=false` downloads provider plugins (needs internet) but
does NOT configure any remote state backend. This is safe for validation only —
no cloud credentials required, no resources created.

`terraform validate` checks:
  - HCL syntax correctness
  - Provider resource and argument schema
  - Required vs. optional argument presence
  - Type correctness of all values

EXIT CODES
──────────
  0  → valid
  1  → invalid (errors printed to stdout/stderr)
"""

from __future__ import annotations

import logging
import os
import shutil
import subprocess
import tempfile
from pathlib import Path

log = logging.getLogger(__name__)

TERRAFORM_DOCKER_IMAGE = "hashicorp/terraform:1.7.5"


def _terraform_binary() -> str | None:
    """Return path to local terraform binary, or None if not installed."""
    return shutil.which("terraform")


def _run_local(cmd: list[str], cwd: str, timeout: int = 120) -> tuple[int, str]:
    """Run a terraform command using the local binary."""
    result = subprocess.run(
        cmd,
        cwd=cwd,
        capture_output=True,
        text=True,
        timeout=timeout,
    )
    output = (result.stdout + result.stderr).strip()
    return result.returncode, output


def _run_docker(cmd: list[str], workspace: str, timeout: int = 180) -> tuple[int, str]:
    """Run a terraform command inside the official Docker image."""
    docker_cmd = [
        "docker", "run", "--rm",
        "--volume", f"{workspace}:/workspace",
        "--workdir", "/workspace",
        TERRAFORM_DOCKER_IMAGE,
    ] + cmd
    result = subprocess.run(
        docker_cmd,
        capture_output=True,
        text=True,
        timeout=timeout,
    )
    output = (result.stdout + result.stderr).strip()
    return result.returncode, output


def _run(subcmd: list[str], workspace: str) -> tuple[int, str]:
    """
    Try local terraform first, fall back to Docker.
    Returns (exit_code, combined_output).
    """
    binary = _terraform_binary()
    if binary:
        log.debug("Using local terraform: %s", binary)
        return _run_local([binary] + subcmd, cwd=workspace)
    else:
        log.debug("terraform not in PATH — using Docker image %s", TERRAFORM_DOCKER_IMAGE)
        return _run_docker(subcmd, workspace=workspace)


def write_files_to_tmpdir(files: dict[str, str]) -> str:
    """
    Write generated .tf files to a temporary directory.
    Returns the temp directory path (caller is responsible for cleanup).
    """
    tmpdir = tempfile.mkdtemp(prefix="iac-gen-")
    for filename, content in files.items():
        path = Path(tmpdir) / filename
        path.write_text(content, encoding="utf-8")
        log.debug("Wrote %d chars to %s", len(content), path)
    return tmpdir


def terraform_init(workspace: str) -> tuple[bool, str]:
    """
    Run `terraform init -backend=false` in workspace.
    Downloads provider plugins (needs internet). No remote state configured.
    Returns (success, output).
    """
    log.info("Running terraform init in %s", workspace)
    code, output = _run(["init", "-backend=false", "-no-color"], workspace)
    if code != 0:
        log.error("terraform init failed (exit %d):\n%s", code, output)
        return False, output
    log.info("terraform init succeeded")
    return True, output


def terraform_validate(workspace: str) -> tuple[bool, str]:
    """
    Run `terraform validate -no-color` in workspace.
    Assumes init has already run (provider schema available).
    Returns (valid, output).
    """
    log.info("Running terraform validate in %s", workspace)
    code, output = _run(["validate", "-no-color"], workspace)
    if code == 0:
        log.info("terraform validate: PASSED")
        return True, output
    log.warning("terraform validate: FAILED\n%s", output)
    return False, output


def validate_generated_files(files: dict[str, str]) -> tuple[bool, str]:
    """
    Full validation pipeline: write files → init → validate → cleanup.

    Returns:
        (passed: bool, output: str)
        output contains the combined terraform messages — errors on failure,
        "Success!" on pass.
    """
    if not files:
        return False, "No files to validate."

    tmpdir = write_files_to_tmpdir(files)
    log.info("Validating %d file(s) in temp dir: %s", len(files), tmpdir)

    try:
        # Step 1: init
        init_ok, init_out = terraform_init(tmpdir)
        if not init_ok:
            return False, f"terraform init failed:\n{init_out}"

        # Step 2: validate
        valid, val_out = terraform_validate(tmpdir)
        return valid, val_out

    except subprocess.TimeoutExpired:
        log.error("terraform timed out")
        return False, "Terraform command timed out after 3 minutes."
    except FileNotFoundError:
        log.error("Neither terraform binary nor Docker found")
        return False, (
            "terraform binary not found and Docker is not available. "
            "Install terraform (https://developer.hashicorp.com/terraform/install) "
            "or Docker to enable validation."
        )
    finally:
        # Clean up temp dir
        import shutil as _shutil
        _shutil.rmtree(tmpdir, ignore_errors=True)
        log.debug("Cleaned up temp dir: %s", tmpdir)
