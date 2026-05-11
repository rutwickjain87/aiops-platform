"""
observability — Shared observability primitives for the AIOps platform.

Exports
───────
  get_logger(name, agent)   JSON-structured logger with correlation ID support
  set_correlation_id(cid)   Inject a correlation ID into the current context
  get_correlation_id()      Read the current correlation ID

Usage
─────
  from observability import get_logger, set_correlation_id
  import uuid

  log = get_logger(__name__, agent="slack-incident-bot")
  set_correlation_id(str(uuid.uuid4()))
  log.info("Alert received", extra={"alert_id": "ALERT-001"})
"""

from observability.logging import get_correlation_id, get_logger, set_correlation_id

__all__ = ["get_logger", "get_correlation_id", "set_correlation_id"]
