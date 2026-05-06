"""
memory_anthropic.py — the agent's notebook (Anthropic SDK format).

Short-term: conversation history as list[dict] — the exact message format
the Anthropic API expects. The two-message format for tool rounds is critical:
  - assistant turn: content blocks including tool_use
  - user turn: content blocks including tool_result
Getting this wrong causes a 400 from the API.

Long-term: vector store stubs (pgvector / Chroma) — wired up on Day 9.

Memory is queried by the planner. Tools never write here directly — the
planner adds tool results to memory after a tool round completes.

USED BY: planner_anthropic.py
SEE ALSO: planner_langchain.py uses LangChain's ChatMessageHistory instead
"""
from __future__ import annotations
from typing import Any


class Memory:
    def __init__(self):
        self._messages: list[dict] = []

    # --- short-term ---
    def add_user(self, text: str) -> None:
        self._messages.append({"role": "user", "content": text})

    def add_assistant(self, text: str) -> None:
        self._messages.append({"role": "assistant", "content": text})

    def add_tool_round(self, assistant_blocks, tool_results: list[dict]) -> None:
        # Anthropic-format: assistant turn (with tool_use blocks) then user turn (tool_result blocks)
        self._messages.append({"role": "assistant", "content": assistant_blocks})
        self._messages.append({
            "role": "user",
            "content": [
                {"type": "tool_result", **r} for r in tool_results
            ],
        })

    def as_messages(self) -> list[dict]:
        return list(self._messages)

    # --- long-term (stub) ---
    def search_long_term(self, query: str, k: int = 5) -> list[dict]:
        """
        Stub. Replace with pgvector / Chroma query on Day 9.
        Returns list of {text, score, source}.
        """
        return []

    def write_long_term(self, text: str, metadata: dict[str, Any]) -> None:
        """Stub. Replace with vector store insert on Day 9."""
        pass
