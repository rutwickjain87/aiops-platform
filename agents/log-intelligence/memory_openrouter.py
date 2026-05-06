"""
memory_openrouter.py — message history in OpenAI/OpenRouter format.

OpenAI message format differs from Anthropic's in two key ways:
  1. System prompt goes INTO the messages list as the first message.
     (Anthropic takes it as a separate `system=` parameter.)
  2. Tool results are a single {"role": "tool", ...} message per result.
     (Anthropic requires TWO messages: assistant turn + user turn.)

OpenAI tool round format:
  assistant: {"role": "assistant", "content": null,
               "tool_calls": [{"id":..., "type":"function",
                               "function":{"name":..., "arguments":"..."}}]}
  tool:      {"role": "tool", "tool_call_id": <id>, "content": "<result>"}

USED BY: planner_openrouter.py
SEE ALSO: memory_anthropic.py — same concept, different message shapes
"""
from __future__ import annotations
from typing import Any


class Memory:
    def __init__(self, system_prompt: str = ""):
        self._messages: list[dict] = []
        if system_prompt:
            self._messages.append({"role": "system", "content": system_prompt})

    # ── short-term ──────────────────────────────────────────────────────────

    def add_user(self, text: str) -> None:
        self._messages.append({"role": "user", "content": text})

    def add_assistant(self, text: str) -> None:
        self._messages.append({"role": "assistant", "content": text})

    def add_tool_round(self, assistant_msg, tool_results: list[dict]) -> None:
        """
        Append the assistant's tool-call message and the tool result messages.

        assistant_msg is the OpenAI ChatCompletionMessage object from the API
        response. We convert it to a plain dict so it can be re-serialised.
        tool_results is a list of {"tool_call_id": ..., "content": ...} dicts
        returned by tools_openrouter.Tools.dispatch().
        """
        # Assistant turn — carry over tool_calls exactly as the API returned them
        self._messages.append({
            "role": "assistant",
            "content": assistant_msg.content,  # often None when tool_calls present
            "tool_calls": [
                {
                    "id": tc.id,
                    "type": "function",
                    "function": {
                        "name": tc.function.name,
                        "arguments": tc.function.arguments,  # raw JSON string
                    },
                }
                for tc in (assistant_msg.tool_calls or [])
            ],
        })
        # One tool message per result
        for r in tool_results:
            self._messages.append({
                "role": "tool",
                "tool_call_id": r["tool_call_id"],
                "content": r["content"],
            })

    def as_messages(self) -> list[dict]:
        return list(self._messages)

    # ── long-term (stub) ────────────────────────────────────────────────────

    def search_long_term(self, query: str, k: int = 5) -> list[dict]:
        """Stub. Replace with pgvector / Chroma query on Day 9."""
        return []

    def write_long_term(self, text: str, metadata: dict[str, Any]) -> None:
        """Stub. Replace with vector store insert on Day 9."""
        pass
