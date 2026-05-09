"""
tracing.py — LangSmith observability layer for the Slack Incident Bot.

WHAT THIS MODULE PROVIDES
──────────────────────────
1. init_tracing_client(anthropic_client)
   Wraps a plain anthropic.Anthropic() instance with LangSmith's
   wrap_anthropic() shim.  Every subsequent messages.create() call is
   automatically logged as a child LLM run under the active trace — no
   other code changes needed.

2. ls_traceable(**kwargs)
   A decorator factory that applies @langsmith.traceable when tracing is
   enabled, and returns the original function unchanged when it is not.
   Use it on any method or function you want to appear as a top-level
   "chain" span in the LangSmith UI.

GRACEFUL DEGRADATION
──────────────────────
If langsmith is not installed, or LANGCHAIN_TRACING_V2 != "true",
both helpers are no-ops — the bot runs exactly as before, with zero
runtime overhead and no ImportError.

REQUIRED ENV VARS (add to .env)
────────────────────────────────
  LANGCHAIN_API_KEY         API key from smith.langchain.com → Settings → API Keys
  LANGCHAIN_TRACING_V2=true Enable tracing (set to "false" to disable)
  LANGCHAIN_PROJECT         Project name shown in LangSmith UI
                            (default: "slack-incident-bot")

WHAT YOU SEE IN LANGSMITH
──────────────────────────
Each call to IncidentPlanner.handle_alert() produces one trace tree:

  ┌─ incident_planner.handle_alert  [chain]
  │    input:  { alert_id: "ALERT-001" }
  │    output: { incident_id: "INC-...", ts: "...", status: "done", iterations: 2 }
  │
  ├─ ChatAnthropic  [llm]   ← first messages.create() — gets alert context
  │    model:  claude-haiku-4-5-20251001
  │    tokens: prompt=412 / completion=87
  │
  └─ ChatAnthropic  [llm]   ← second messages.create() — posts incident card
       model:  claude-haiku-4-5-20251001
       tokens: prompt=631 / completion=143
"""

from __future__ import annotations

import logging
import os
from typing import Any, Callable, TypeVar

logger = logging.getLogger(__name__)

F = TypeVar("F", bound=Callable[..., Any])

# ── Optional LangSmith import ─────────────────────────────────────────────────
# All LangSmith symbols are imported lazily so the module is importable
# even when the package is not installed.

try:
    from langsmith.wrappers import wrap_anthropic as _wrap_anthropic
    from langsmith import traceable as _ls_traceable

    _LANGSMITH_AVAILABLE = True
except ImportError:
    _LANGSMITH_AVAILABLE = False
    logger.debug("langsmith package not installed — tracing is disabled")


# ── Public helpers ────────────────────────────────────────────────────────────


def tracing_enabled() -> bool:
    """Return True when LangSmith is installed and tracing env var is set to true.

    Supports both the current name (LANGSMITH_TRACING) and the legacy name
    (LANGCHAIN_TRACING_V2) so either works in .env.
    """
    if not _LANGSMITH_AVAILABLE:
        return False
    # New canonical name (langsmith >= 0.2)
    new_var = os.environ.get("LANGSMITH_TRACING", "").lower()
    # Legacy name still accepted
    old_var = os.environ.get("LANGCHAIN_TRACING_V2", "").lower()
    return new_var == "true" or old_var == "true"


def init_tracing_client(anthropic_client: Any) -> Any:
    """Return a LangSmith-wrapped Anthropic client, or the original if tracing is off.

    Args:
        anthropic_client: A plain ``anthropic.Anthropic()`` instance.

    Returns:
        The same client wrapped with ``wrap_anthropic()`` when tracing is
        enabled, or the original client unchanged when it is not.

    Example::

        import anthropic
        from tracing import init_tracing_client

        client = init_tracing_client(anthropic.Anthropic())
        # All client.messages.create() calls are now auto-traced to LangSmith.
    """
    if not tracing_enabled():
        return anthropic_client

    project = os.environ.get("LANGSMITH_PROJECT") or os.environ.get("LANGCHAIN_PROJECT", "slack-incident-bot")
    logger.info("LangSmith tracing ENABLED — project: %s", project)
    return _wrap_anthropic(anthropic_client)


def ls_traceable(
    fn: F | None = None,
    *,
    name: str | None = None,
    run_type: str = "chain",
    tags: list[str] | None = None,
) -> F | Callable[[F], F]:
    """Decorator (factory) that adds a LangSmith parent span when tracing is on.

    When tracing is disabled the decorated function is returned unchanged.
    Supports both bare ``@ls_traceable`` and parametrised
    ``@ls_traceable(name="...", tags=[...])`` usage.

    Args:
        fn:        The function to decorate (set automatically for bare usage).
        name:      Span name shown in LangSmith.  Defaults to ``fn.__name__``.
        run_type:  LangSmith run type — "chain", "llm", "tool", etc.
        tags:      Optional list of string tags to attach to the run.

    Example::

        @ls_traceable(name="incident_planner.handle_alert", tags=["slack-bot"])
        def handle_alert(self, alert_id: str) -> dict:
            ...
    """

    def decorator(func: F) -> F:
        if not tracing_enabled():
            return func

        span_name = name or func.__name__
        kwargs: dict[str, Any] = {"run_type": run_type, "name": span_name}
        if tags:
            kwargs["tags"] = tags

        return _ls_traceable(**kwargs)(func)  # type: ignore[return-value]

    if fn is not None:
        # Called as bare @ls_traceable — decorate immediately
        return decorator(fn)

    # Called as @ls_traceable(...) — return the decorator
    return decorator
