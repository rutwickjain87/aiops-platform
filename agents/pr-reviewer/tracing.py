"""
tracing.py — LangSmith observability for the PR Reviewer agent.

WHAT THIS TEACHES
─────────────────
The PR Reviewer uses LangChain (ChatAnthropic via langchain_anthropic).
LangChain has native LangSmith integration — every model call is automatically
traced when LANGSMITH_TRACING=true, with no code changes required at the call
site.

This module adds the one thing LangChain doesn't do automatically: a top-level
parent span for the full review run so you see:

  pr_reviewer.run  [chain]
    ├─ ChatAnthropic [llm]  ← fetch_pr_diff turn
    ├─ ChatAnthropic [llm]  ← run_semgrep turn(s)
    └─ ChatAnthropic [llm]  ← final synthesis turn

Without this wrapper the LLM calls appear as orphaned root spans.

CONTRAST WITH SLACK-INCIDENT-BOT
─────────────────────────────────
The slack-incident-bot uses the raw Anthropic SDK (not LangChain), so it needs
wrap_anthropic() to intercept messages.create() calls.  The PR reviewer doesn't
need that — LangChain does it automatically.

ENV VARS
────────
  LANGSMITH_TRACING=true        Enable tracing (default: false)
  LANGSMITH_API_KEY=ls-...      Your LangSmith API key
  LANGSMITH_PROJECT=aiops-pr    Project name shown in LangSmith UI
"""

from __future__ import annotations

import logging

logger = logging.getLogger(__name__)

# ── Optional LangSmith import ─────────────────────────────────────────────────

try:
    from langsmith import traceable as _traceable

    _LANGSMITH_AVAILABLE = True
except ImportError:  # pragma: no cover
    _LANGSMITH_AVAILABLE = False
    logger.debug("langsmith not installed — tracing disabled")


# ── Public decorator factory ──────────────────────────────────────────────────


def ls_traceable(
    fn=None,
    *,
    name: str | None = None,
    run_type: str = "chain",
    tags: list[str] | None = None,
):
    """Decorator factory that applies @langsmith.traceable when tracing is enabled.

    When LANGSMITH_TRACING is not set or langsmith is not installed, this is a
    no-op and the original function is returned unchanged.

    Supports both bare usage and parametrised usage::

        @ls_traceable                              # bare
        def run(self, ...): ...

        @ls_traceable(name="pr_reviewer.run", tags=["pr-reviewer"])
        def run(self, ...): ...
    """
    def decorator(func):
        if not _LANGSMITH_AVAILABLE:
            return func
        return _traceable(
            name=name or func.__name__,
            run_type=run_type,
            tags=tags or [],
        )(func)

    if fn is not None:
        # Called as @ls_traceable (no parens) — fn is the decorated function
        return decorator(fn)
    # Called as @ls_traceable(...) — return the decorator
    return decorator
