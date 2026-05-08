"""
Day 1 — your first ReAct agent loop.

WHAT YOU'LL LEARN BY RUNNING THIS:
- The agent loop (request → tool_use → tool_result → request → end_turn)
- How tool-calling actually works under the hood
- That "the LLM provider is just a config swap" — same logical agent runs
  via Anthropic's native SDK and via OpenRouter's OpenAI-compatible API.

PREREQUISITES (per SETUP.md):
- ANTHROPIC_API_KEY exported in your shell
- OPENROUTER_API_KEY exported in your shell
- Python 3.11+ via pyenv
- `uv pip install anthropic openai python-dotenv`

RUN:
    cd aiops-platform/agents/_scratch
    uv venv && source .venv/bin/activate
    uv pip install anthropic openai python-dotenv
    python day1_loop.py

EXPECTED OUTPUT (timestamps will differ):
    === via Anthropic SDK direct ===
    The current UTC time is 2026-04-30T...

    === via OpenRouter ===
    The current UTC time is 2026-04-30T...
"""

from __future__ import annotations
import os
import sys
from datetime import datetime, timezone

# Optional: load .env if present (not required if env vars are set in shell)
try:
    from dotenv import load_dotenv

    # Try the platform .env first, then fall back to shell env
    for env_path in ["../../.env", "../../../.env", ".env"]:
        if os.path.exists(env_path):
            load_dotenv(env_path)
            break
except ImportError:
    pass


# ─── The "tool" the agent will call ────────────────────────────────────────


def get_current_time() -> str:
    """Return the current UTC time as an ISO-8601 string. The agent will call this."""
    return datetime.now(timezone.utc).isoformat()


def get_weather(city: str) -> str:
    """Return a hardcoded weather string for the given city."""
    return f"The weather in {city} is sunny and 32°C. (hardcoded stub)"


# Tool schema — same logical contract for both providers.
TOOL_SCHEMA_ANTHROPIC = [
    {
        "name": "get_current_time",
        "description": "Return the current UTC time as an ISO-8601 string.",
        "input_schema": {"type": "object", "properties": {}, "required": []},
    },
    {
        "name": "get_weather",
        "description": "Return the current weather for a given city.",
        "input_schema": {
            "type": "object",
            "properties": {"city": {"type": "string", "description": "The city name"}},
            "required": ["city"],
        },
    },
]

TOOL_SCHEMA_OPENAI_FORMAT = [
    {
        "type": "function",
        "function": {
            "name": "get_current_time",
            "description": "Return the current UTC time as an ISO-8601 string.",
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_weather",
            "description": "Return the current weather for a given city.",
            "parameters": {
                "type": "object",
                "properties": {
                    "city": {"type": "string", "description": "The city name"}
                },
                "required": ["city"],
            },
        },
    },
]

SYSTEM_PROMPT = (
    "You are a helpful assistant. When the user asks for the time, "
    "you MUST call the get_current_time tool. Then return a friendly "
    "one-sentence answer that includes the time."
)

USER_PROMPT = "What is the current UTC time and what is the weather like in Mumbai?"


# ─── Backend 1: Anthropic SDK direct ───────────────────────────────────────


def run_via_anthropic(prompt: str, model: str = "claude-haiku-4-5-20251001") -> str:
    """Run the agent loop using Anthropic's native SDK."""
    from anthropic import Anthropic

    client = Anthropic()
    messages = [{"role": "user", "content": prompt}]

    for step in range(10):  # cap steps to prevent runaway
        resp = client.messages.create(
            model=model,
            max_tokens=1024,
            system=SYSTEM_PROMPT,
            tools=TOOL_SCHEMA_ANTHROPIC,
            messages=messages,
        )

        # End of turn: return the final text
        if resp.stop_reason == "end_turn":
            return "".join(b.text for b in resp.content if b.type == "text")

        # Tool use: execute the tool and feed result back
        if resp.stop_reason == "tool_use":
            tool_results = []
            for block in resp.content:
                if block.type == "tool_use":
                    if block.name == "get_current_time":
                        result = get_current_time()
                    elif block.name == "get_weather":
                        import json

                        args = (
                            json.loads(block.input)
                            if isinstance(block.input, str)
                            else block.input
                        )
                        result = get_weather(args["city"])
                    else:
                        result = f"unknown tool: {block.name}"
                    tool_results.append(
                        {
                            "type": "tool_result",
                            "tool_use_id": block.id,
                            "content": result,
                        }
                    )
            messages.append({"role": "assistant", "content": resp.content})
            messages.append({"role": "user", "content": tool_results})
            continue

        raise RuntimeError(f"unexpected stop_reason: {resp.stop_reason}")

    raise RuntimeError("step limit reached")


# ─── Backend 2: OpenRouter (OpenAI-compatible API) ─────────────────────────


def run_via_openrouter(prompt: str, model: str = "anthropic/claude-haiku-4-5") -> str:
    """Run the same logical agent via OpenRouter — only the client config changes."""
    from openai import OpenAI

    client = OpenAI(
        base_url="https://openrouter.ai/api/v1",
        api_key=os.environ["OPENROUTER_API_KEY"],
    )

    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": prompt},
    ]

    for step in range(10):
        resp = client.chat.completions.create(
            model=model,
            messages=messages,
            tools=TOOL_SCHEMA_OPENAI_FORMAT,
            max_tokens=512,  # keep low — free tier has limited credits; 512 is plenty for this task
            # Optional but recommended — these show up in the OpenRouter dashboard
            extra_headers={
                "HTTP-Referer": "https://github.com/your-username/aiops-platform",
                "X-Title": "aiops-platform-day1",
            },
        )
        msg = resp.choices[0].message

        if not msg.tool_calls:
            return msg.content

        # OpenAI format: append the assistant message, then one tool message per call
        messages.append(
            {
                "role": "assistant",
                "content": msg.content or "",
                "tool_calls": [
                    {
                        "id": tc.id,
                        "type": "function",
                        "function": {
                            "name": tc.function.name,
                            "arguments": tc.function.arguments,
                        },
                    }
                    for tc in msg.tool_calls
                ],
            }
        )
        for tc in msg.tool_calls:
            if tc.function.name == "get_current_time":
                result = get_current_time()
            elif tc.function.name == "get_weather":
                import json

                args = json.loads(tc.function.arguments)
                result = get_weather(args["city"])
            else:
                result = f"unknown tool: {tc.function.name}"
            messages.append({"role": "tool", "tool_call_id": tc.id, "content": result})

    raise RuntimeError("step limit reached")


# ─── Run both ───────────────────────────────────────────────────────────────


def main() -> int:
    if "ANTHROPIC_API_KEY" not in os.environ:
        print("ERROR: ANTHROPIC_API_KEY not set. See SETUP.md §5.1.", file=sys.stderr)
        return 1
    if "OPENROUTER_API_KEY" not in os.environ:
        print(
            "ERROR: OPENROUTER_API_KEY not set. See SETUP.md Day 1 §OpenRouter.",
            file=sys.stderr,
        )
        return 1

    print("=== via Anthropic SDK direct ===")
    print(run_via_anthropic(USER_PROMPT))
    print()
    print("=== via OpenRouter ===")
    print(run_via_openrouter(USER_PROMPT))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
