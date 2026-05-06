"""
tools_openrouter.py — tools in OpenAI/OpenRouter function-calling format.

Same three tool functions as tools_anthropic.py (grep, read_log_chunk,
cluster_errors). The difference is in the schema() and dispatch() methods:

  tools_anthropic.py                  tools_openrouter.py
  ────────────────────────────────    ──────────────────────────────────────
  "input_schema": {...}               "function": {"parameters": {...}}
  block.type == "tool_use"            tc.function.name (OpenAI ChatCompletion)
  block.input (dict)                  json.loads(tc.function.arguments)
  {"type": "tool_result", ...}        {"role": "tool", "tool_call_id": ...}

USED BY: planner_openrouter.py
SEE ALSO: tools_anthropic.py for the Anthropic-format equivalent
"""
from __future__ import annotations
import json
import subprocess
from pathlib import Path
from collections import defaultdict
from datetime import datetime
from pydantic import BaseModel, Field


# ── Tool functions (identical logic to tools_anthropic.py) ─────────────────

class GrepIn(BaseModel):
    pattern: str = Field(..., description="Regex pattern (ripgrep syntax) to search for")
    path: str = Field(..., description="Absolute path to the file to search")


def grep(args: GrepIn) -> str:
    out = subprocess.run(
        ["rg", "--no-heading", "-n", args.pattern, args.path],
        capture_output=True, text=True, timeout=10,
    )
    result = out.stdout.strip()
    if not result:
        return f"(no matches for pattern '{args.pattern}' in {args.path})"
    lines = result.splitlines()
    if len(lines) > 200:
        return "\n".join(lines[:200]) + f"\n... ({len(lines) - 200} more lines truncated)"
    return result


class ReadLogChunkIn(BaseModel):
    path: str = Field(..., description="Absolute path to the log file")
    start_line: int = Field(1, description="Line number to start reading from (1-indexed)")
    num_lines: int = Field(100, description="Number of lines to read (max 500)")


def read_log_chunk(args: ReadLogChunkIn) -> str:
    p = Path(args.path)
    if not p.exists():
        return f"ERROR: file not found: {args.path}"
    num_lines = min(args.num_lines, 500)
    start = max(1, args.start_line)
    all_lines = p.read_text(errors="replace").splitlines()
    total = len(all_lines)
    chunk = all_lines[start - 1 : start - 1 + num_lines]
    return f"[Lines {start}–{start + len(chunk) - 1} of {total}]\n" + "\n".join(chunk)


class ClusterErrorsIn(BaseModel):
    path: str = Field(..., description="Absolute path to the log file")
    window_minutes: int = Field(10, description="Size of the time bucket in minutes")


def cluster_errors(args: ClusterErrorsIn) -> str:
    p = Path(args.path)
    if not p.exists():
        return f"ERROR: file not found: {args.path}"
    bucket_minutes = max(1, args.window_minutes)
    buckets: dict[str, list[str]] = defaultdict(list)
    unparsed: list[str] = []
    for line in p.read_text(errors="replace").splitlines():
        upper = line.upper()
        if not any(level in upper for level in ("WARN", "ERROR", "FATAL")):
            continue
        ts = _parse_timestamp(line)
        if ts:
            mins = ts.hour * 60 + ts.minute
            bucket_start = (mins // bucket_minutes) * bucket_minutes
            key = f"{ts.strftime('%Y-%m-%d')} {bucket_start // 60:02d}:{bucket_start % 60:02d}"
            buckets[key].append(line)
        else:
            unparsed.append(line)
    if not buckets and not unparsed:
        return f"No WARN/ERROR/FATAL lines found in {args.path}"
    parts = [f"Clustered anomalies from {p.name} (window={bucket_minutes}min)\n"]
    for key in sorted(buckets):
        entries = buckets[key]
        parts.append(f"\n[{key}] — {len(entries)} event(s)")
        for e in entries[:5]:
            parts.append(f"  {e}")
        if len(entries) > 5:
            parts.append(f"  ... ({len(entries) - 5} more)")
    if unparsed:
        parts.append(f"\n[unparsed] — {len(unparsed)} event(s)")
        for e in unparsed[:5]:
            parts.append(f"  {e}")
    return "\n".join(parts)


def _parse_timestamp(line: str) -> datetime | None:
    parts = line.split()
    if len(parts) < 2:
        return None
    if len(parts[0]) == 6 and parts[0].isdigit() and len(parts[1]) == 6 and parts[1].isdigit():
        try:
            return datetime.strptime(parts[0] + parts[1], "%y%m%d%H%M%S")
        except ValueError:
            pass
    for fmt in ("%Y-%m-%dT%H:%M:%S", "%Y-%m-%d %H:%M:%S"):
        try:
            ts_str = parts[0] + " " + parts[1] if "T" not in parts[0] else parts[0]
            return datetime.strptime(ts_str, fmt)
        except ValueError:
            pass
    return None


# ── Registry / dispatch — OpenAI function-calling format ───────────────────

class Tools:
    """
    Same _registry pattern as tools_anthropic.py, but schema() returns
    OpenAI function-calling format and dispatch() processes OpenAI tool_calls.

    OpenAI schema format:
      {"type": "function", "function": {"name": ..., "description": ..., "parameters": <JSON Schema>}}

    Anthropic schema format:
      {"name": ..., "description": ..., "input_schema": <JSON Schema>}

    The JSON Schema body is identical — only the wrapper differs.
    """
    _registry: dict[str, tuple] = {
        "grep": (
            GrepIn, grep,
            "Search a log file for lines matching a regex pattern. Returns matching lines with line numbers.",
        ),
        "read_log_chunk": (
            ReadLogChunkIn, read_log_chunk,
            "Read a contiguous block of lines from a log file. Use this for initial inspection or to examine a specific section.",
        ),
        "cluster_errors": (
            ClusterErrorsIn, cluster_errors,
            "Group WARN/ERROR/FATAL lines into time buckets to spot bursts or cascading failures.",
        ),
    }

    def schema(self) -> list[dict]:
        """Return OpenAI function-calling format tool schemas."""
        return [
            {
                "type": "function",
                "function": {
                    "name": name,
                    "description": desc,
                    "parameters": model.model_json_schema(),
                },
            }
            for name, (model, _fn, desc) in self._registry.items()
        ]

    def dispatch(self, tool_calls) -> list[dict]:
        """
        Execute tool calls from an OpenAI API response.
        tool_calls is resp.choices[0].message.tool_calls — a list of
        ChatCompletionMessageToolCall objects.
        Returns a list of {"tool_call_id": ..., "content": ...} dicts.
        """
        results = []
        for tc in (tool_calls or []):
            name = tc.function.name
            if name not in self._registry:
                results.append({
                    "tool_call_id": tc.id,
                    "content": f"ERROR: unknown tool '{name}'",
                })
                continue
            model_cls, fn, _ = self._registry[name]
            try:
                args = json.loads(tc.function.arguments)
                validated = model_cls.model_validate(args)
                output = fn(validated)
                results.append({"tool_call_id": tc.id, "content": str(output)})
            except Exception as e:
                results.append({"tool_call_id": tc.id, "content": f"ERROR: {e}"})
        return results
