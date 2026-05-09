# AIOps Platform — Learning Journal

---

## Day 1 — Platform Scaffolding + First ReAct Agent Loop

**Date:** 3 May 2026
**Commit:** `b1996e7`

---

### What We Built

**Repo skeleton** — complete platform structure created in one commit: `.gitignore`, `.env.example`, `LICENSE`, `README.md`, `CONTRIBUTING.md`, `SECURITY.md`, `CODE_OF_CONDUCT.md`, `CHANGELOG.md`, GitHub issue templates, PR template, `architecture/system-design.md`, and `docs/postmortems/incident-001.md`.

**`SETUP.md` and `SCHEDULE.md`** — documented prerequisites (pyenv, uv, API keys), expected Day 1 output, and the full learning schedule for Days 1–11. These were written up front so every day had a clear definition of done.

**Two GitHub Actions workflows (initial versions):**
- `test.yaml` — pytest + ruff lint/format, triggered on push and PR
- `eval.yaml` — eval runner skeleton, triggered on PR and nightly schedule

**`agents/_scratch/day1_loop.py`** — the first working ReAct agent. A minimal loop implementing the full agent cycle (`request → tool_use → tool_result → request → end_turn`) using two toy tools:
- `get_current_time()` — returns UTC ISO-8601 timestamp
- `get_weather(city)` — hardcoded stub returning a fake weather string

The same logical agent runs against two providers to demonstrate that the provider is just a config swap:
- **Anthropic SDK** — `anthropic.Anthropic().messages.create()` with `input_schema` tool format
- **OpenRouter** — `openai.OpenAI(base_url="https://openrouter.ai/api/v1")` with `function.parameters` format

---

### Key Concepts Learned

**The agent loop is a `while True` with two exit conditions.** Every ReAct agent — regardless of framework or provider — is fundamentally: call the LLM → if `stop_reason == "end_turn"` return the answer → if `stop_reason == "tool_use"` execute tools → append results → repeat. Frameworks like LangChain are abstractions over this loop, not replacements for understanding it.

**Tool schemas differ by provider but the logic is identical.** Anthropic uses `input_schema` (JSON Schema nested under the tool dict); OpenAI/OpenRouter uses `function.parameters`. The tool execution code is the same either way — only the schema wrapper and the response parsing differ.

**Message history is the agent's memory.** There is no hidden state. The entire "memory" of a multi-turn agent is the list of messages passed to each API call. Adding `{"role": "tool", "content": result}` is how the agent learns what a tool returned. This mental model carries forward to every agent built afterwards.

**Environment setup matters more than it looks.** `uv` for Python env management, `pyenv` for Python version pinning, and a `.env.example` documenting required keys are foundational — not nice-to-haves. Starting with them avoids "works on my machine" issues across dev/CI from day one.

---

### Misses & What Could Be Better

The toy tools (`get_current_time`, `get_weather`) were useful for understanding the loop but gave no intuition for what makes a good tool in a real agent. A more useful Day 1 exercise would use a real file-reading tool so the distinction between "LLM reasoning" and "tool execution" is immediately concrete.

No tests on Day 1. The workflows existed but the test suite was empty — which meant CI passed vacuously. This set a bad habit of treating CI green as meaningful before any tests were written.

---

## Day 2 — Log Triage Agent (Three Backends)

**Date:** 7 May 2026
**Commit:** `fad91c0`

---

### What We Built

**`agents/log-intelligence/`** — a production-structured log triage agent that reads an HDFS log file, clusters anomalies by time window, and emits a structured Markdown report with Severity, Root Cause Hypothesis, and Suggested Actions sections.

Three fully independent, swappable backends sharing the same logical agent:

| Backend | Planner | Tools | Memory | Client |
|---------|---------|-------|--------|--------|
| `--backend anthropic` | `planner_anthropic.py` | `tools_anthropic.py` (registry pattern) | `memory_anthropic.py` (list[dict]) | `anthropic.Anthropic()` |
| `--backend langchain` | `planner_langchain.py` | `@tool` decorators inline | LangChain messages | `ChatAnthropic.bind_tools()` |
| `--backend openrouter` | `planner_openrouter.py` | `tools_openrouter.py` (OpenAI format) | `memory_openrouter.py` (system in messages) | `openai.OpenAI(base_url=openrouter)` |

Three domain-specific tools:
- `read_log_chunk(path, start_line, num_lines)` — paginated file reader; the agent can scan large logs without loading them whole
- `grep_log(path, pattern, max_matches)` — regex search returning matching lines with line numbers
- `cluster_errors(matches)` — groups log entries into 60-second time windows to surface burst patterns

**Evaluator + eval cases** — `evaluator.py` runs an agent against `evals/cases.jsonl` (5 HDFS test cases) and scores each output with a configurable rubric. Initial rubric: `contains` — checks that the expected string appears in the agent's output. All three backends passed 5/5.

**SDK comparison infographic** — a visual side-by-side of the three backend implementations showing how the same logical agent maps to different SDK primitives (tool schema format, stop_reason field names, memory message types). Built as a reference artefact, not just notes.

**loghub-samples** — added as a git submodule pointing to the loghub dataset repo for realistic HDFS log fixtures. *(This became the source of Day 4's most painful CI bug.)*

---

### Key Concepts Learned

**Separating planner, tools, and memory is the right abstraction.** Each file has one job. The planner owns the loop and LLM calls. The tools own execution and error handling. Memory owns message history formatting. This separation makes it straightforward to swap backends without touching the tool logic.

**The Anthropic SDK tool registry pattern vs LangChain `@tool`.** The raw SDK requires manually defining `input_schema` dicts and dispatching by tool name. LangChain's `@tool` decorator auto-generates the schema from the function signature and docstring. Both work; LangChain is less boilerplate but more magic. Knowing the raw SDK first means you understand what LangChain is hiding.

**Tool docstrings directly affect LLM behaviour.** The description in a tool's docstring (or `description` field in the schema) is what the LLM reads to decide whether and how to call the tool. Vague descriptions produce wrong calls; precise descriptions with argument semantics produce correct ones. This surfaced again in Day 4 when "Absolute path to file" in a tool docstring caused Claude to refuse tool calls when given a relative path.

**`stop_reason` is the loop control.** For Anthropic SDK: `end_turn` = done, `tool_use` = execute tools. For LangChain: empty `tool_calls` list = done. For OpenRouter (OpenAI format): `finish_reason == "stop"` = done, `finish_reason == "tool_calls"` = execute. Same logic, different field names.

**Memory per backend is a design decision, not a framework concern.** Anthropic messages are `list[dict]` with role/content. LangChain uses typed message objects (`HumanMessage`, `AIMessage`, `ToolMessage`). OpenRouter follows the OpenAI format with `system` as the first message. Each backend's memory module handles the translation so the planner logic stays clean.

---

### Misses & What Could Be Better

**Git submodule was the wrong choice for loghub-samples.** Adding an external dataset repo as a submodule without a `.gitmodules` file created a broken gitlink that CI couldn't resolve. Plain tracked files (with `git add -f` to bypass `*.log` gitignore) would have been simpler from the start. The submodule was only ever needed because `*.log` was in `.gitignore` — a rule that didn't account for test fixtures.

**No LangSmith tracing wired up.** The LangChain backend could emit traces to LangSmith with one env var but this wasn't configured. Losing observability on the most complex backend from the start made debugging harder.

**Eval cases used absolute Mac paths.** `cases.jsonl` hardcoded `/Users/advaita/workspace/...` as the log file path. This passed locally but failed immediately on any other machine or in CI. Should have used repo-relative paths from day one and resolved them to absolute at runtime.

---

## Day 3 — Model Routing Experiment (Sonnet vs Haiku vs GPT-4o Mini)

**Date:** 8 May 2026
**Commits:** `0f6b9b7`, then CI fixes `71dac54` → `7a2c3e9` → `eb9ce63` → `61d6514` → `00b078a`

---

### What We Built

**`agents/log-intelligence/run_experiment.py`** — a multi-model benchmarking harness that runs the log triage evaluator against all 5 HDFS cases for each configured model, records per-case latency, token counts, and cost, and writes both a quantitative summary table and qualitative triage outputs to `experiments/outputs/`.

**Three models benchmarked** against the same 5 eval cases on `HDFS_2k.log`:

| Model | Pass rate | p50 latency | Avg cost/run |
|-------|-----------|-------------|--------------|
| Claude Sonnet 4.6 | 5/5 (100%) | 56 s | $0.333 |
| Claude Haiku 4.5 | 5/5 (100%) | 18 s | $0.017 |
| GPT-4o Mini | 5/5 (100%) | 12 s | $0.003 |

**`experiments/` directory** — structured output storage: `log-triage-model-routing.md` (raw results), `log-triage-model-routing-analysis.md` (qualitative analysis), and `outputs/` with per-model triage reports.

**Day 3 infographic** — visual summary of the three-model routing decision: pass rate, latency, cost, and token depth side-by-side, with the recommended routing strategy annotated.

**`questionnaire/questionnaire-day1-to-day3.html`** — 30-question MCQ covering everything from Days 1–3: the ReAct loop, tool schema differences between providers, eval rubric design, model routing trade-offs, and CI pitfalls. Self-grading HTML artifact — open in a browser to test recall.

**CI infrastructure** (required before Day 3 experiment could run cleanly in CI):
- Root `requirements.txt` — ruff, pytest, pytest-cov, pydantic
- `pytest.ini` — testpaths, norecursedirs to exclude `.venv` dirs
- `ruff.toml` — per-file-ignores for agents/scripts, excludes `.venv` from lint
- `Makefile` — `make eval`, `make test`, `make lint`, `make fmt`, `make setup` targets
- `tests/test_evaluator.py` (12 unit tests) and `tests/test_experiment.py` (14 unit tests) — no API keys required, fast

---

### Key Concepts Learned

**Pass rate is a misleading metric when tool depth varies.** All three models scored 5/5, but GPT-4o Mini averaged only 14.7k input tokens per case — the HDFS log alone is ~80k tokens. A model that scores 100% while barely reading the input file is pattern-matching on domain knowledge, not performing genuine log analysis. The `contains` rubric is necessary but not sufficient. Token depth (how many tool calls, how many log lines actually read) is an equally important signal.

**Cost vs quality trade-off is non-linear.** Haiku is 19× cheaper and 3× faster than Sonnet for the same pass rate on this task. The quality difference is real (Sonnet produces more specific root cause citations and longer action lists) but not worth 19× cost for routine P3/P4 triage. This points directly to a tiered routing strategy.

**Routing strategy:** Haiku for all alerts, Sonnet reserved for P1/P2 escalation. At a 10% P1/P2 rate, blended cost ≈ $0.049/run — 85% cheaper than Sonnet-for-everything while preserving deep analysis for high-severity incidents.

**`ruff` is strict by default and will fail CI on things you wouldn't notice locally.** Day 3 CI failures were entirely lint issues: `E741` (ambiguous variable name `l`), `F401` (unused imports left in after refactoring), `F541` (f-strings with no placeholders), `I001` (import sort order), `E401` (multiple imports on one line). None of these break runtime behaviour — all of them break CI. The fix: run `ruff check .` and `ruff format --check .` locally before every push.

**GitHub Actions `paths:` filters mean failed re-runs may be checking out a stale commit.** `eval.yaml` only triggers on changes to `agents/**`, `evals/**`, `services/**`. Pushing `requirements.txt` alone never triggered a fresh eval run — every "eval failed" result during Day 3 was a re-run of the original old job (run `25544964261`) checking out a pre-fix commit. The fix was committed; only then did a push touching `agents/**` trigger a genuinely fresh run against the current code. Lesson: when CI keeps failing despite local fixes, check the triggering commit SHA — if it's stale, a fresh trigger (touching a file in the paths filter) is needed.

**GitHub Actions Node.js version warnings need proactive management.** `setup-uv@v3` used Node.js 20 (deprecated in GitHub Actions), causing workflow warnings on every run. Fix: bump to `setup-uv@v6` (Node.js 24 native) and set `FORCE_JAVASCRIPT_ACTIONS_TO_NODE24: true` in the workflow env block. Small thing, but warning noise in CI makes real failures harder to spot.

**Unit tests that require no API keys are a forcing function for good design.** `test_evaluator.py` and `test_experiment.py` test the evaluation and experiment logic with mock agents and in-memory fixtures. Writing these tests forced cleaner separation between the agent (which needs API keys) and the evaluation harness (which doesn't). This paid off immediately when CI ran 45 tests in seconds without touching the Anthropic API.

---

### Misses & What Could Be Better

**GPT-4o Mini's shallow tool usage wasn't caught during development** — it only became visible when token counts were compared side-by-side. A richer eval rubric (e.g. requiring a minimum number of tool calls, or checking that specific log line timestamps appear in the output) would have caught this automatically.

**The experiment harness wasn't in CI** — `run_experiment.py` was only run manually. An experiment that lives outside CI drifts from the codebase over time. Ideally the nightly eval workflow would also run the cost/quality benchmark on a fixed seed so regressions are caught automatically.

**Ruff fixes took five separate commits** (`7a2c3e9` → `eb9ce63` → `61d6514` → `00b078a`). Running `ruff check . && ruff format --check .` before the initial commit would have caught all of these in one pass. The habit of "push and see what CI says" is expensive when each round-trip takes 3–5 minutes.

---

## Day 4 — PR Security Reviewer Agent + CI Eval Pipeline

**Date:** May 2026
**Branch:** `feat/incident-api-service` → merged to `main`

---

### What We Built

**agents/pr-reviewer/** — A second ReAct agent applying the same Day 2 pattern (plan → tool call → observe → repeat) to a new domain: automated PR security review on every GitHub pull request.

Three LangChain `@tool` functions:
- `fetch_pr_diff` — pulls the full PR diff via PyGitHub, caps per-file patches and total file count to stay within API rate limits
- `run_semgrep` — runs SAST analysis on each changed file's code snippet, returns structured findings
- `post_review_comment` — posts (or idempotently updates) a Markdown security report as a PR comment, using an HTML marker `<!-- ai-reviewer:v1 -->` so there is always exactly one bot comment per PR

The planner (`planner.py`) runs an explicit ReAct loop via LangChain's `bind_tools`, synthesises Semgrep findings with LLM reasoning, and formats a structured report with severity, CWE IDs, explanations, and suggested fixes.

**CI eval pipeline** — Wired the Day 2 log-intelligence agent into a proper automated eval suite:
- `evaluator.py` — generic evaluator that runs an agent factory against a set of cases and scores each output
- `agents/log-intelligence/evals/cases.jsonl` — 5 test cases checking the agent produces correct triage report sections
- `scripts/run_eval_ci.py` — CI runner that resolves paths, invokes the evaluator, writes `evals/results/latest.json`, and exits non-zero if pass rate < 80%

**Three GitHub Actions workflows brought to green:**
- `test.yaml` — pytest (45/45) + ruff lint + ruff format check
- `eval.yaml` — agent eval suite (5/5, 100%), posts results as PR comment, runs nightly
- `ai-review.yml` — PR security reviewer, posts review on every PR open/sync/reopen

---

### Key Concepts Learned

**ReAct pattern is domain-agnostic.** The same loop structure from Day 2 (log triage) applies directly to PR security review — only the tools and system prompt change. The planner code is nearly identical. This confirms ReAct as a reusable architectural pattern, not a one-off trick.

**LangChain `bind_tools` vs explicit tool loop.** Using `bind_tools` with an explicit iteration loop (rather than a pre-built agent) gives fine-grained control: you can inspect each tool call, add logging, set iteration caps, and handle errors per-call without fighting the framework.

**Idempotent GitHub comments via HTML markers.** Embedding `<!-- ai-reviewer:v1 -->` in every comment and searching for it before posting means the PR timeline stays clean across multiple workflow runs. This pattern is broadly applicable anywhere you want "one managed comment per PR."

**GitHub Actions token permissions must be explicit.** The default `GITHUB_TOKEN` is read-only. Posting PR comments requires `issues: write` and `pull-requests: write` declared at the workflow level in a `permissions:` block. Without it, you get a silent 403.

**Venv activation in CI is fragile; explicit paths are not.** `source .venv/bin/activate` in a GitHub Actions `run:` step can silently fail and fall through to the system Python when the path doesn't exist — because `set -e` is not on by default. The safe pattern is `$VENV/bin/python script.py` using the absolute venv Python path directly, never relying on shell activation.

**`uv pip install --python <path>` over `source activate + uv pip`.** When managing multiple venvs in one CI step, using `--python` explicitly targets the right interpreter without any directory changes or activation. Avoids the ambiguity of which venv is "active" after `cd`.

**`os.chdir()` breaks relative output paths.** `run_eval_ci.py` changed directory to `AGENT_DIR` so relative imports worked, but this silently moved the output file to the wrong location. Fix: `output_path = Path(args.output).resolve()` before `os.chdir()` captures the absolute path while the cwd is still the repo root.

**Git submodules without `.gitmodules` are a broken state.** The loghub-samples directory was a gitlink (mode 160000) with no `.gitmodules` file — a leftover from a detached submodule setup. CI checked out an empty directory. Converting to plain tracked files required: `git rm --cached <path>` to remove the gitlink, `rm -rf <path>/.git` to remove the nested repo, then `git add -f <path>/` to force-add past the `*.log` gitignore rule.

**`*.log` in `.gitignore` blocks legitimate log fixtures.** The gitignore rule `*.log` blocked the loghub sample `.log` files needed by the eval suite. Fix: add `!services/ingestion/loghub-samples/**` exception after the `*.log` rule, and use `git add -f` to force-stage files that match a gitignore pattern.

**Anthropic API rate limits are per-minute input tokens.** The org-level ceiling (50k input tokens/minute on the free tier) is easily hit by a PR reviewer processing a large diff across many files. Mitigations: cap `MAX_PATCH_CHARS` per file, cap `MAX_FILES` reviewed, catch `anthropic.RateLimitError` and post a graceful fallback comment rather than failing CI.

---

### Architecture Decision: Production PR Reviewer

The Day 4 agent is a working prototype. A production-grade version requires three architectural layers:

1. **Triage (rule-based)** — classify files by risk before any LLM call; skip docs, focus on auth/DB/API routes
2. **Deep review (full file context)** — fetch full file content for high-risk files, not just the diff patch; route to Sonnet for high-risk, Haiku for medium-risk
3. **Async via GitHub Check Runs** — never block the PR merge queue; set check to `in_progress` immediately, update when done

Full details captured in `pr-reviewer-arch-guidelines.docx`.

---

### CI Bugs Fixed (in order encountered)

| Bug | Root Cause | Fix |
|-----|-----------|-----|
| Ruff I001 import order (4 errors) | Unsorted imports in incident-api service | `ruff check --select I001 --fix` |
| Ruff format (24 files) | Code style across whole repo | `ruff format .` |
| `ImportError: TOOL_MAP` | tools.py had `@tool` functions but no exports | Added `TOOLS` list and `TOOL_MAP` dict at module bottom |
| `ImportError: AnthropicPlanner` | planner_anthropic.py exports `Planner`, eval imports `AnthropicPlanner` | Added aliases at bottom of file |
| `ImportError: langchain_core` in test.yaml | Root test venv missing langchain_core needed by tools.py | Install `agents/pr-reviewer/requirements.txt` in root venv |
| `TypeError: Memory() unexpected kwarg` | run_eval_ci.py passed `system_prompt=SYSTEM_PROMPT` but Memory takes no args | `Memory()` with no args |
| `ZeroDivisionError` in evaluator | `passed / total` when total == 0 | Guard: `pct = passed / total * 100 if total else 0.0` |
| Eval 0/5 — hardcoded Mac path in cases.jsonl | Absolute path only valid on dev machine | Changed to relative path, resolved to absolute in run_eval_ci.py |
| Eval 0/5 — agent not using tools (relative path) | Tool docstring said "Absolute path"; Claude refused tool calls on `../../` path | Resolve to absolute before passing to agent |
| Eval 0/5 — HDFS log file missing in CI | services/ingestion/loghub-samples was a broken git submodule | Remove gitlink, delete nested .git, `git add -f` to track as plain files |
| 403 on PR comment posting (both workflows) | GITHUB_TOKEN is read-only by default | Add `permissions: issues: write, pull-requests: write` block |
| Eval output written to wrong directory | `os.chdir(AGENT_DIR)` before `Path(args.output)` resolves | Resolve output path to absolute before chdir |
| `RateLimitError` crash in ai-review | Large PR diff exceeded 50k input tokens/minute | Cap MAX_PATCH_CHARS + MAX_FILES; catch RateLimitError, post fallback comment, exit 0 |
| `No module named 'anthropic'` in eval nightly | `source .venv/bin/activate` silently fell through to system Python | Use `$AGENT_PYTHON scripts/...` with explicit venv path; no shell activation |

---

### Current Status

- `test.yaml` ✅ passing (45/45 pytest, ruff clean)
- `eval.yaml` ✅ eval logic passing (5/5); nightly run fix pushed to main, awaiting confirmation
- `ai-review.yml` ✅ passing (rate limit handled gracefully)

**Next:** Day 5

---

## Day 5 — Slack Incident Bot + LangSmith Observability

**Date:** 2026-05-08
**Theme:** Real-time Slack agent with end-to-end LangSmith tracing

---

### What Was Built

**Slack Incident Bot** — a production-style Slack Socket Mode bot that:
- Listens for `@incident ALERT-ID` mentions and `!trigger ALERT-ID` CLI commands
- Runs a ReAct loop (Anthropic SDK, `claude-haiku-4-5-20251001`) that calls two tools in sequence:
  1. `get_alert_context(alert_id)` — looks up alert metadata from a local store
  2. `post_incident_card(...)` — formats and posts a structured Slack Block Kit card
- Posts a rich incident card (severity badge, title, runbook link, acknowledgement button) to a configured Slack channel

Agent entrypoint: `agents/slack-incident-bot/`
Key files: `app.py`, `planner.py`, `tools.py`, `memory.py`, `tracing.py`

**LangSmith Observability Layer** — `tracing.py` wraps the bot with full trace visibility:
- `init_tracing_client(anthropic_client)` — wraps the plain `anthropic.Anthropic()` client with `langsmith.wrappers.wrap_anthropic()` so every `messages.create()` call is auto-traced as a child LLM run
- `ls_traceable(name, run_type, tags)` — decorator factory that applies `@langsmith.traceable` when tracing is enabled; returns the original function unchanged when disabled (no-op)
- Every `handle_alert()` call appears in LangSmith as one trace tree:

```
incident_planner.handle_alert  [chain]
  ├─ ChatAnthropic [llm]  ← get_alert_context turn (prompt + completion tokens)
  └─ ChatAnthropic [llm]  ← post_incident_card turn (prompt + completion tokens)
```

**Makefile multi-venv overhaul** — the root Makefile now manages two fully independent venvs:
- `agents/log-intelligence/.venv` (for Day 2 log agent)
- `agents/slack-incident-bot/.venv` (for Day 5 bot)

Targets added: `setup-log`, `setup-bot`, `test-log`, `test-bot`; guard checks print a helpful message and exit 1 if the venv binary is missing rather than a cryptic `No such file` from make.

**Bot test suite** — 24 unit tests in `tests/test_slack_bot.py`:
- Planner logic: ReAct loop, tool dispatch, `post_incident_card` extraction from tool result
- Tools: alert lookup, incident card Slack API call mocking, idempotent update
- Graceful degradation: all tests pass with `langsmith` installed or absent

---

### Key Concepts Learned

**`wrap_anthropic()` is zero-config tracing.** LangSmith's `wrap_anthropic(client)` shim intercepts every `messages.create()` call transparently — no changes to the call site. All token counts, latency, model name, and prompt/response content appear automatically. The only requirement is a `LANGSMITH_API_KEY` and `LANGSMITH_TRACING=true` in the environment.

**`LANGSMITH_*` vs `LANGCHAIN_*` env var naming.** LangSmith SDK ≥ 0.2 renamed the environment variables:
- `LANGCHAIN_TRACING_V2=true` → `LANGSMITH_TRACING=true`
- `LANGCHAIN_API_KEY` → `LANGSMITH_API_KEY`
- `LANGCHAIN_PROJECT` → `LANGSMITH_PROJECT`

The old names still work as a fallback, but the LangSmith UI now shows the new names. `tracing.py` checks both so either works in `.env`.

**Graceful degradation with optional packages.** Wrapping the `from langsmith import ...` block in `try/except ImportError` and gating all behaviour on `_LANGSMITH_AVAILABLE` means the module is always importable. Tests don't need to mock the package away — they run the same code paths regardless of whether `langsmith` is installed.

**Decorator factories must handle both bare and parametrised usage.** `@ls_traceable` (no parens) passes the function as the first argument; `@ls_traceable(name="...")` must return a decorator. The pattern `if fn is not None: return decorator(fn)` handles both cases without requiring two separate functions.

**Sandbox-built venvs are never portable.** Python shebang lines in `.venv/bin/python` are absolute paths baked at creation time. A venv created inside the sandbox (`/sessions/vigilant-lucid-darwin/...`) will not work on the Mac. Always delete any sandbox-created venv and recreate it locally with `make setup-bot`.

**`uv pip install --python <path>` keeps multi-agent deps isolated.** Using `uv pip install -r requirements.txt --python .venv/bin/python` inside each agent directory installs deps into that agent's venv without activating it globally — safe to run from the repo root Makefile without directory-change side effects.

**Slack Socket Mode requires two tokens.** `SLACK_APP_TOKEN` (xapp-) enables Socket Mode (WebSocket connection to Slack's RTM servers); `SLACK_BOT_TOKEN` (xoxb-) authenticates API calls (posting messages, fetching user info). Both are required; confusing them produces a silent authentication failure.

---

### Architecture: Observability in the Agent Loop

```
handle_alert(alert_id)                        ← @ls_traceable parent span
│
├─ client.messages.create(...)                ← auto-traced by wrap_anthropic()
│    stop_reason = "tool_use"
│    block.name  = "get_alert_context"
│
├─ _dispatch("get_alert_context", {alert_id}) ← plain Python, no trace span needed
│
├─ client.messages.create(...)                ← auto-traced (2nd LLM turn)
│    stop_reason = "tool_use"
│    block.name  = "post_incident_card"
│
├─ _dispatch("post_incident_card", {...})     ← Slack API call
│
└─ client.messages.create(...)                ← auto-traced (final turn)
     stop_reason = "end_turn"
     → return {"incident_id": ..., "status": "done", "iterations": 3}
```

The chain span captures total latency and I/O; the nested LLM runs capture per-turn token usage and model name. This gives a complete cost and latency breakdown per incident in the LangSmith UI.

---

### Bugs Fixed (in order encountered)

| Bug | Root Cause | Fix |
|-----|-----------|-----|
| `zsh: command not found: pytest` | System Python used, bot venv not activated | Activate venv: `source agents/slack-incident-bot/.venv/bin/activate` or use `make test-bot` |
| `bad interpreter: /sessions/vigilant-lucid-darwin/...` | Venv created in sandbox with sandbox-specific shebang | `rm -rf agents/slack-incident-bot/.venv && make setup-bot` on local Mac |
| `zsh: no such file or directory: .venv/bin/pytest` | `pytest` not in `requirements.txt`; venv never created locally | Added `pytest>=8.0` + `pytest-cov>=5.0` to `requirements.txt`; run `make setup-bot` |
| `make test` fails on `test-log` (no log venv) | `test` depends on both `test-log` and `test-bot`; log venv not built | Added guard: if `$(LOG_PYTEST)` doesn't exist, print message and `exit 1` |
| LangSmith "Waiting for traces..." | `.env` used old `LANGCHAIN_TRACING_V2` / `LANGCHAIN_API_KEY` names; LangSmith SDK now expects `LANGSMITH_*` | Updated `tracing.py` to check both; updated `.env` to use new canonical names |
| `export VAR="value"` in `.env` | Shell syntax in dotenv file; `python-dotenv` requires `KEY=value` | Rewrote `.env` to plain `KEY=value` format; removed all `export` prefixes |

---

### Current Status

- `agents/slack-incident-bot/tracing.py` ✅ LangSmith integration with graceful fallback
- `agents/slack-incident-bot/planner.py` ✅ `@ls_traceable` + `init_tracing_client` wired in
- `agents/slack-incident-bot/requirements.txt` ✅ `langsmith>=0.1.77` added
- `agents/slack-incident-bot/.env.example` ✅ updated to `LANGSMITH_*` variable names
- `Makefile` ✅ multi-venv targets: `setup-bot`, `test-bot`, `setup-log`, `test-log`
- `SETUP.md` / `SCHEDULE.md` ✅ restored to `aiops-platform/` root (originals from Day 1)
- `docs/setup.md` ✅ Day 5 Slack + LangSmith setup guide
- `docs/schedule.md` ✅ daily ops runbook with morning health checks

**Pending (run locally):**
```bash
# 1. Rebuild bot venv on Mac (sandbox venv won't work)
make setup-bot

# 2. Run the 24-test suite
make test-bot

# 3. Test live tracing (ensure .env has LANGSMITH_* keys set)
cd agents/slack-incident-bot
python app.py --trigger ALERT-001

# 4. Commit all Day 5 work
git add agents/slack-incident-bot/tracing.py \
        agents/slack-incident-bot/planner.py \
        agents/slack-incident-bot/requirements.txt \
        agents/slack-incident-bot/.env.example \
        docs/setup.md docs/schedule.md \
        SETUP.md SCHEDULE.md Makefile \
        README.md CONTRIBUTING.md JOURNAL.md
git commit -m "feat(day5): Slack incident bot + LangSmith tracing + Makefile multi-venv"
git push
```

**Next:** Day 6
