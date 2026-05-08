"""
bad_pr.py — Deliberately vulnerable code used to validate the PR security reviewer.

DO NOT USE IN PRODUCTION. This file exists solely as a test fixture.

It intentionally contains:
  CWE-798  Hardcoded AWS credential (line ~20)
  CWE-89   SQL injection via f-string interpolation (line ~35)
  CWE-94   Code injection via eval() on user input (line ~50)
  CWE-78   OS command injection via shell=True (line ~62)
  CWE-22   Path traversal via unsanitised filename (line ~75)

The PR security reviewer agent should detect all five classes.
"""
import os
import sqlite3
import subprocess

# ── CWE-798: Hardcoded Credential ─────────────────────────────────────────────
# Never hardcode secrets. Use environment variables or a secret manager.
AWS_ACCESS_KEY_ID = "AKIAIOSFODNN7EXAMPLE"          # noqa: S105
AWS_SECRET_ACCESS_KEY = "wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY"  # noqa: S105
DATABASE_PASSWORD = "super_secret_db_password_123"  # noqa: S105


# ── CWE-89: SQL Injection ──────────────────────────────────────────────────────
def get_user(conn: sqlite3.Connection, username: str) -> list:
    """Fetch a user record — VULNERABLE: raw string interpolation in SQL."""
    # WRONG: attacker can pass username = "' OR '1'='1"
    query = f"SELECT * FROM users WHERE username = '{username}'"
    cursor = conn.execute(query)
    return cursor.fetchall()


def safe_get_user(conn: sqlite3.Connection, username: str) -> list:
    """Fixed version using parameterised query."""
    cursor = conn.execute("SELECT * FROM users WHERE username = ?", (username,))
    return cursor.fetchall()


# ── CWE-94: Code Injection via eval() ─────────────────────────────────────────
def calculate(expression: str) -> object:
    """Evaluate a maths expression from user input — VULNERABLE: arbitrary code exec."""
    # WRONG: eval() on untrusted input allows arbitrary Python execution
    # e.g. expression = "__import__('os').system('rm -rf /')"
    return eval(expression)  # noqa: S307


def safe_calculate(expression: str) -> float:
    """Fixed version using ast.literal_eval (safe for literals) or a maths parser."""
    import ast
    # For real calculators, use a dedicated safe expression evaluator.
    return float(ast.literal_eval(expression))


# ── CWE-78: OS Command Injection ──────────────────────────────────────────────
def ping_host(hostname: str) -> str:
    """Ping a host — VULNERABLE: shell=True with unsanitised input."""
    # WRONG: attacker can pass hostname = "localhost; rm -rf /"
    result = subprocess.run(
        f"ping -c 1 {hostname}",
        shell=True,          # noqa: S602
        capture_output=True,
        text=True,
    )
    return result.stdout


def safe_ping_host(hostname: str) -> str:
    """Fixed version using argument list (no shell interpolation)."""
    result = subprocess.run(
        ["ping", "-c", "1", hostname],
        capture_output=True,
        text=True,
        timeout=5,
    )
    return result.stdout


# ── CWE-22: Path Traversal ────────────────────────────────────────────────────
BASE_DIR = "/var/app/uploads"


def read_user_file(filename: str) -> str:
    """Read a file from the uploads directory — VULNERABLE: path traversal."""
    # WRONG: attacker can pass filename = "../../etc/passwd"
    path = os.path.join(BASE_DIR, filename)
    with open(path) as f:  # noqa: PTH123
        return f.read()


def safe_read_user_file(filename: str) -> str:
    """Fixed version with path canonicalisation and containment check."""
    path = os.path.realpath(os.path.join(BASE_DIR, filename))
    if not path.startswith(os.path.realpath(BASE_DIR) + os.sep):
        raise ValueError(f"Path traversal detected: {filename!r}")
    with open(path) as f:  # noqa: PTH123
        return f.read()
