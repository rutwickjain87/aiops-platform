"""
observability/logging.py — JSON-structured logging for the AIOps platform.

WHAT THIS PROVIDES
──────────────────
A single factory function, get_logger(), that returns a standard Python logger
pre-configured with a JSON formatter.  Every log record emits a JSON object on
one line, making it trivially ingestible by Loki, CloudWatch, Datadog, or any
log aggregator that understands newline-delimited JSON (NDJSON).

SAMPLE OUTPUT
─────────────
{"timestamp": "2026-05-11T09:42:01.234Z", "level": "INFO",
 "logger": "planner", "agent": "slack-incident-bot",
 "correlation_id": "a3f2b1c0-...", "message": "Alert received",
 "alert_id": "ALERT-001"}

CORRELATION IDs
───────────────
A correlation ID ties all log lines for a single request together.  Set it once
at the start of each request and every subsequent log line in that context
automatically carries it:

  from observability.logging import set_correlation_id, get_logger
  import uuid

  set_correlation_id(str(uuid.uuid4()))
  log = get_logger(__name__, agent="slack-incident-bot")
  log.info("handle_alert started", extra={"alert_id": alert_id})

The correlation ID is stored in a contextvars.ContextVar, so it is naturally
isolated per async task / thread — safe for concurrent workloads.

GRACEFUL DEGRADATION
────────────────────
If python-json-logger is not installed the module falls back to the standard
Python formatter (human-readable text) — the logger is always returned, just
without JSON encoding.

REQUIRED PACKAGE
────────────────
  pip install python-json-logger>=2.0.0   # add to shared requirements or each
                                           # agent's requirements.txt
"""

from __future__ import annotations

import logging
import sys
from contextvars import ContextVar
from typing import Any

# ── Optional JSON formatter ────────────────────────────────────────────────────

try:
    try:
        from pythonjsonlogger.json import JsonFormatter as _JsonFormatter  # >=3.x
    except ImportError:
        from pythonjsonlogger.jsonlogger import JsonFormatter as _JsonFormatter  # 2.x

    _JSON_AVAILABLE = True
except ImportError:  # pragma: no cover
    _JSON_AVAILABLE = False

# ── Correlation ID context variable ───────────────────────────────────────────

_correlation_id: ContextVar[str] = ContextVar("correlation_id", default="-")


def set_correlation_id(cid: str) -> None:
    """Set the correlation ID for the current execution context.

    Args:
        cid: A unique identifier for the current request/alert (e.g. UUID4).
    """
    _correlation_id.set(cid)


def get_correlation_id() -> str:
    """Return the correlation ID for the current execution context."""
    return _correlation_id.get()


# ── JSON log record factory ────────────────────────────────────────────────────


class _CorrelationFilter(logging.Filter):
    """Injects correlation_id and agent into every LogRecord."""

    def __init__(self, agent: str) -> None:
        super().__init__()
        self._agent = agent

    def filter(self, record: logging.LogRecord) -> bool:  # noqa: A003
        record.correlation_id = _correlation_id.get()
        record.agent = self._agent
        return True


# ── Public factory ─────────────────────────────────────────────────────────────

# Track loggers we've already configured to avoid double-handler attachment.
_configured: set[str] = set()


def get_logger(
    name: str,
    agent: str = "aiops",
    level: int = logging.INFO,
) -> logging.Logger:
    """Return a JSON-structured logger for the given module and agent.

    The logger emits one JSON object per line with these standard fields:
      timestamp, level, logger, agent, correlation_id, message
    plus any ``extra`` kwargs you pass to log calls.

    Args:
        name:  Module name — pass ``__name__`` from the calling module.
        agent: Human-readable agent label, e.g. "slack-incident-bot".
        level: Logging level (default: INFO).

    Returns:
        Configured :class:`logging.Logger` instance.

    Example::

        log = get_logger(__name__, agent="pr-reviewer")
        log.info("Review started", extra={"pr": 42, "repo": "org/repo"})
    """
    logger = logging.getLogger(name)

    if name in _configured:
        return logger  # already set up — avoid duplicate handlers

    logger.setLevel(level)
    logger.propagate = False  # don't double-print via root logger

    handler = logging.StreamHandler(sys.stdout)

    if _JSON_AVAILABLE:
        fmt = _JsonFormatter(
            fmt="%(asctime)s %(levelname)s %(name)s %(agent)s %(correlation_id)s %(message)s",
            rename_fields={
                "levelname": "level",
                "name": "logger",
                "asctime": "timestamp",
            },
            datefmt="%Y-%m-%dT%H:%M:%SZ",
        )
    else:
        # Fallback: human-readable with key fields
        fmt = logging.Formatter(
            fmt="%(asctime)s [%(levelname)s] %(name)s agent=%(agent)s "
                "cid=%(correlation_id)s — %(message)s",
            datefmt="%Y-%m-%dT%H:%M:%S",
        )

    handler.setFormatter(fmt)
    handler.addFilter(_CorrelationFilter(agent=agent))
    logger.addHandler(handler)

    _configured.add(name)
    return logger


def _extra(**kwargs: Any) -> dict[str, Any]:
    """Convenience helper: build an ``extra`` dict for structured log fields.

    Usage::

        log.info("Tool called", extra=_extra(tool="get_alert_context", alert_id=aid))
    """
    return kwargs
