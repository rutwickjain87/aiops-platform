"""
tools_anthropic.py — the hands of the agent (Anthropic SDK format).

Every external effect lives here. Tools are typed (Pydantic in, str out).
Tools NEVER read the system prompt and NEVER modify memory directly.

The _registry dict maps tool name → (InputModel, function, description).
planner_anthropic.py calls Tools.schema() to get the Anthropic-format tool
definitions, and Tools.dispatch() to route tool_use blocks to real functions.

Available tools:
  - grep              Search a log file with ripgrep (regex).
  - read_log_chunk    Read N lines from a log file starting at a given line.
  - cluster_errors    Group WARN/ERROR/FATAL lines into time windows.

Add a new tool:
  1. Define a Pydantic input model.
  2. Implement the function (returns a str).
  3. Register it in Tools._registry.

USED BY: planner_anthropic.py
SEE ALSO: planner_langchain.py — same tool logic but wrapped with @tool decorator
"""
from __future__ import annotations
import subprocess
from pathlib import Path
from collections import defaultdict
from datetime import datetime
from pydantic import BaseModel, Field


# ── Tool: grep ─────────────────────────────────────────────────────────────

class GrepIn(BaseModel):
    pattern: str = Field(..., description="Regex pattern (ripgrep syntax) to search for")
    path: str = Field(..., description="Absolute path to the file to search")


def grep(args: GrepIn) -> str:
    """Search a file with ripgrep. Returns matching lines with line numbers."""
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


# ── Tool: read_log_chunk ────────────────────────────────────────────────────

class ReadLogChunkIn(BaseModel):
    path: str = Field(..., description="Absolute path to the log file")
    start_line: int = Field(1, description="Line number to start reading from (1-indexed)")
    num_lines: int = Field(100, description="Number of lines to read (max 500)")


def read_log_chunk(args: ReadLogChunkIn) -> str:
    """Read a chunk of lines from a log file. Useful for initial inspection or deep-dives."""
    p = Path(args.path)
    if not p.exists():
        return f"ERROR: file not found: {args.path}"
    num_lines = min(args.num_lines, 500)
    start = max(1, args.start_line)
    all_lines = p.read_text(errors="replace").splitlines()
    total = len(all_lines)
    chunk = all_lines[start - 1 : start - 1 + num_lines]
    return f"[Lines {start}–{start + len(chunk) - 1} of {total}]\n" + "\n".join(chunk)


# ── Tool: cluster_errors ───────────────────────────────────────────────────

class ClusterErrorsIn(BaseModel):
    path: str = Field(..., description="Absolute path to the log file")
    window_minutes: int = Field(
        10,
        description="Size of the time bucket in minutes. Lines with WARN/ERROR/FATAL are grouped into buckets of this width.",
    )


def cluster_errors(args: ClusterErrorsIn) -> str:
    """
    Parse WARN/ERROR/FATAL lines, group them into time buckets, and return
    a summary. Supports HDFS-style timestamps (YYMMDD HHMMSS) and ISO 8601.
    """
    p = Path(args.path)
    if not p.exists():
        return f"ERROR: file not found: {args.path}"

    bucket_minutes = max(1, args.window_minutes)
    buckets: dict[str, list[str]] = defaultdict(list)
    unparsed_errors: list[str] = []

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
            unparsed_errors.append(line)

    if not buckets and not unparsed_errors:
        return f"No WARN/ERROR/FATAL lines found in {args.path}"

    parts: list[str] = [f"Clustered anomaly lines from {p.name} (window={bucket_minutes}min)\n"]
    for key in sorted(buckets):
        entries = buckets[key]
        parts.append(f"\n[{key}] — {len(entries)} event(s)")
        for e in entries[:5]:
            parts.append(f"  {e}")
        if len(entries) > 5:
            parts.append(f"  ... ({len(entries) - 5} more in this window)")
    if unparsed_errors:
        parts.append(f"\n[unparsed timestamp] — {len(unparsed_errors)} event(s)")
        for e in unparsed_errors[:5]:
            parts.append(f"  {e}")
    return "\n".join(parts)


def _parse_timestamp(line: str) -> datetime | None:
    """Try to extract a datetime from common log timestamp formats."""
    parts = line.split()
    if len(parts) < 2:
        return None
    # HDFS format: 081109 214043
    if len(parts[0]) == 6 and parts[0].isdigit() and len(parts[1]) == 6 and parts[1].isdigit():
        try:
            return datetime.strptime(parts[0] + parts[1], "%y%m%d%H%M%S")
        except ValueError:
            pass
    # ISO 8601
    for fmt in ("%Y-%m-%dT%H:%M:%S", "%Y-%m-%d %H:%M:%S"):
        try:
            ts_str = parts[0] + " " + parts[1] if "T" not in parts[0] else parts[0]
            return datetime.strptime(ts_str, fmt)
        except ValueError:
            pass
    return None


# ── Registry / dispatch ─────────────────────────────────────────────────────

class Tools:
    """
    Dispatcher. Maps Anthropic tool_use blocks → real Python functions.

    The _registry dict is the single source of truth for tool names,
    input schemas, and descriptions. The planner never sees the functions —
    only the schema (name + description + JSON schema for inputs).
    """
    _registry: dict[str, tuple] = {
        "grep": (
            GrepIn,
            grep,
            "Search a log file for lines matching a regex pattern. Returns matching lines with line numbers.",
        ),
        "read_log_chunk": (
            ReadLogChunkIn,
            read_log_chunk,
            "Read a contiguous block of lines from a log file. Use this for initial inspection or to examine a specific section.",
        ),
        "cluster_errors": (
            ClusterErrorsIn,
            cluster_errors,
            "Group WARN/ERROR/FATAL lines into time buckets to spot bursts or cascading failures.",
        ),
    }

    def schema(self) -> list[dict]:
        """Return Anthropic-format tool schemas for all registered tools."""
        return [
            {
                "name": name,
                "description": desc,
                "input_schema": model.model_json_schema(),
            }
            for name, (model, _fn, desc) in self._registry.items()
        ]

    def dispatch(self, content_blocks) -> list[dict]:
        """Execute tool calls from an Anthropic API response."""
        results = []
        for block in content_blocks:
            if block.type != "tool_use":
                continue
            if block.name not in self._registry:
                results.append({
                    "tool_use_id": block.id,
                    "content": f"ERROR: unknown tool '{block.name}'",
                    "is_error": True,
                })
                continue
            model, fn, _desc = self._registry[block.name]
            try:
                validated = model.model_validate(block.input)
                output = fn(validated)
                results.append({"tool_use_id": block.id, "content": str(output)})
            except Exception as e:
                results.append({
                    "tool_use_id": block.id,
                    "content": f"ERROR: {e}",
                    "is_error": True,
                })
        return results
