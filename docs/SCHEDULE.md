# 11-Day Schedule — Phase 1 Build (v3: Provider-Agnostic, OpenSRE-Optional)

> **v3 — supersedes v2 ([`SCHEDULE-v1.md`](SCHEDULE-v1.md) is the original 14-day version).** Key shifts from v2:
> 1. **OpenSRE demoted.** No longer a structural dependency. Kept as an optional reference — and Day 7 has an optional OpenSRE PR task if you want the open-source contribution signal.
> 2. **OpenRouter added from Day 1.** Single API for Anthropic, OpenAI, Mistral, Llama, Gemini. Provider-agnostic agent design from the start.
> 3. **Days 1–3 restructured.** Freed time from OpenSRE goes into building faster and deeper eval discipline.
> 4. **Day 7 adds optional OpenSRE PR.** Browse issues, pick one, submit — it's a bonus credential, not a blocker.
> 5. **Day 11 comparison is now multi-provider** (5 models via OpenRouter), not just Ollama vs Sonnet.

> **Companion docs:** [`AGENTIC_AI_ROADMAP.md`](../AGENTIC_AI_ROADMAP.md) · [`PORTFOLIO_STRATEGY.md`](../PORTFOLIO_STRATEGY.md) · [`SETUP.md`](SETUP.md) · [`GITHUB_SETUP.md`](../GITHUB_SETUP.md)
>
> **Workspace root:** `~/workspace/claude-code/ai-journey/agentic-ai-projects/`
> All relative paths in this file are relative to the workspace root unless stated otherwise.
>
> **⚠️ Prerequisite:** Complete [`SETUP.md`](SETUP.md) before Day 1. The Pre-Day-1 verification at the bottom of SETUP.md is the gate — running `day1_loop.py` successfully proves your environment is ready.

---

## How to use this schedule

- **One day = one focused block** (~6–8 hours). Don't context-switch mid-day.
- **Each day has 5 sections:** Goal · Topic · Tasks · Progress check · Tips. Some days also have **📁 Starter scaffold** pointing at pre-built code.
- **Work inside `aiops-platform/` from Day 1.** New agent? `aiops-platform/agents/`. New tool? `aiops-platform/services/`.
- **Mark progress in this file.** `🔲` → `✅` as you go.
- **One journal entry per day in `aiops-platform/JOURNAL.md`** — what worked / what didn't / surprise.

## Starter scaffolds (already in your workspace)

These files exist already — read them before running them.

| Day | File | What it is |
|---|---|---|
| 1 | [`aiops-platform/agents/_scratch/day1_loop.py`](aiops-platform/agents/_scratch/day1_loop.py) | Smallest possible ReAct agent, called via Anthropic SDK *and* OpenRouter. The point: feel the loop. |
| 1 | [`aiops-platform/agents/_scratch/README.md`](aiops-platform/agents/_scratch/README.md) | Explains the `_scratch/` convention. |
| 2+ | [`_templates/agent-skeleton/`](_templates/agent-skeleton/) | Standard `planner.py` / `tools.py` / `memory.py` / `evaluator.py` / `main.py` to copy into each new agent. |
| any | [`_templates/PROJECT_README_TEMPLATE.md`](_templates/PROJECT_README_TEMPLATE.md) | Senior-signal README template (Problem · Architecture · Metrics · Failure Modes). |
| any | [`_templates/RUNBOOK_TEMPLATE.md`](_templates/RUNBOOK_TEMPLATE.md) | Runbook template — fill in per agent. |
| any | [`_templates/POSTMORTEM_TEMPLATE.md`](_templates/POSTMORTEM_TEMPLATE.md) | Postmortem template. |

---

## The framework map

| Framework / Tool | Role | Days |
|---|---|---|
| **Anthropic API** | Primary model (Sonnet 4.6 for planning, Haiku 4.5 for cheap loops) | All days |
| **OpenRouter** | Multi-provider access layer — Anthropic + OpenAI + Mistral + Llama via one API | All days (Day 1 setup, active from Day 3) |
| **LangChain** | Tool-calling agents, simple ReAct loops, integrations | 2, 3, 4, 5 |
| **LangGraph** | State-machine agents, branching, retries, multi-step planning | 6, 7, 8, 9, 10 |
| **CrewAI** | Multi-agent orchestration with role-playing specialists | 9, 10 |
| **Ollama** | Local fallback model for offline iteration | 1 (setup), 8 |
| **OpenSRE** | Optional reference architecture — skim if curious, don't depend on it | Optional (Day 1 setup, Day 7 PR optional) |

---

## Week-at-a-glance

| Day | Theme | Output | Difficulty |
|---|---|---|---|
| 1 | Foundations + Full Toolchain + First Agent Loop | Toolchain wired, OpenRouter + Anthropic both callable, first ReAct agent runs | Beginner |
| 2 | Log Triage Agent — Build | CLI agent produces a structured triage report on real logs | Beginner |
| 3 | Log Triage — Eval + First Model Routing Experiment | Eval ≥80%, first OpenRouter model comparison logged | Beginner |
| 4 | PR Security Reviewer (LangChain + GitHub Actions) | Bot reviews real PRs, cites CWEs, idempotent | Beginner |
| 5 | Slack Incident Bot + Observability (LangSmith + Prom) | Reaction → channel + full traces visible | Intermediate |
| 6 | K8s Doctor Foundation (LangGraph) | Diagnoses CrashLoopBackOff via state-machine pipeline | Intermediate |
| 7 | K8s Doctor Polish + Multi-Model Routing (+ Optional: OpenSRE PR) | 3 failure modes + model routing experiment + optional upstream PR | Intermediate |
| 8 | SAST Auto-Fixer + IaC Generator | One auto-PR + Terraform from NL (OpenRouter for cheap iteration) | Intermediate |
| 9 | Alert Correlator + Multi-Agent SRE Team start (CrewAI) | Synthetic correlation + 4 agents tracing | Intermediate→Advanced |
| 10 | Multi-Agent finish + Pentest Agent (lab) | E2E incident response + pentest finds 1+ CVE | Advanced |
| 11 | Demos + Micro-SaaS scaffold + Multi-Provider Comparison | 3 flagship gifs + SaaS skeleton + OpenRouter benchmark published | Advanced |

---

## Day 1 — Foundations + Full Toolchain + First Agent Loop

🎯 **Goal:** Conceptual map of agents in your head. OpenRouter and Anthropic both callable. Your first ReAct agent loop felt in your hands — not just read about.

📚 **Topic of the day:** What an agent loop *is* (workflow vs. agent). Tool-calling as the fundamental primitive. How OpenRouter enables provider-agnostic design.

⚙️ **Tasks:**

- 🔲 Read [Anthropic — "Building effective agents"](https://www.anthropic.com/engineering/building-effective-agents) (45 min) — *don't skip this*
- 🔲 Skim [MCP introduction](https://modelcontextprotocol.io/introduction) (20 min)
- 🔲 Install full toolchain — see `SETUP.md` Day 1 section:
  - `pyenv` + Python 3.11, `uv`, `node`
  - Ollama + `llama3.2:3b`
  - Docker, `kind`, `kubectl`, `helm`, `k9s`
- 🔲 Get **Anthropic API key** — set **$30 monthly cap** in console NOW
- 🔲 Get **OpenRouter API key** at [openrouter.ai/keys](https://openrouter.ai/keys)
- 🔲 Add both to `~/.zshrc`:
  ```bash
  export ANTHROPIC_API_KEY="sk-ant-..."
  export OPENROUTER_API_KEY="sk-or-..."
  ```
- 🔲 Verify OpenRouter works:
  ```bash
  curl https://openrouter.ai/api/v1/chat/completions \
    -H "Authorization: Bearer $OPENROUTER_API_KEY" \
    -H "Content-Type: application/json" \
    -d '{"model": "anthropic/claude-haiku-4-5", "messages": [{"role": "user", "content": "ping"}]}'
  ```
- 🔲 **Optional — install OpenSRE** (reference only, not a sprint dependency):
  ```bash
  git clone https://github.com/Tracer-Cloud/opensre \
    ~/workspace/claude-code/ai-journey/opensre-upstream
  cd ~/workspace/claude-code/ai-journey/opensre-upstream
  curl -fsSL https://raw.githubusercontent.com/Tracer-Cloud/opensre/main/install.sh | bash
  opensre onboard
  opensre investigate -i tests/e2e/kubernetes/fixtures/datadog_k8s_alert.json
  ```
- 🔲 Build your **first ReAct agent** — the starter is already at [`aiops-platform/agents/_scratch/day1_loop.py`](aiops-platform/agents/_scratch/day1_loop.py):
  - **Read the file first** (it's ~150 lines, fully commented). Understand each section before running.
  - Install and run:
    ```bash
    cd ~/workspace/claude-code/ai-journey/agentic-ai-projects/aiops-platform/agents/_scratch
    uv venv && source .venv/bin/activate
    uv pip install -r requirements.txt
    python day1_loop.py
    ```
  - **Expected output** — you should see two clearly separated blocks:
    ```
    === via Anthropic SDK direct ===
    [tool call] get_current_time()
    [tool result] <timestamp>
    The current time is HH:MM:SS.

    === via OpenRouter ===
    [tool call] get_current_time()
    [tool result] <timestamp>
    The current time is HH:MM:SS.
    ```
    Both blocks must appear. Each must show a tool call + tool result + a final natural-language answer. The exact wording of the answer will vary — that's fine.
  - **If it fails:**
    - `401 Unauthorized` → API key not exported in current shell (`echo $ANTHROPIC_API_KEY`)
    - `404` or `Connection refused` → wrong base URL or OpenRouter key not set
    - `ModuleNotFoundError` → `uv pip install -r requirements.txt` wasn't run in the active venv
  - **Then modify it.** Add a second tool (e.g., `get_weather(city)` that returns a hardcoded string). See it called. The point: feel the loop in your fingers; see that "the provider is just a config swap."
- 🔲 Create `aiops-platform/` skeleton:
  ```bash
  cd ~/workspace/claude-code/ai-journey/agentic-ai-projects/aiops-platform
  mkdir -p agents services infra observability experiments docs demos
  touch JOURNAL.md
  git add . && git commit -m "chore: Day 1 skeleton — platform dirs + JOURNAL"
  git push
  ```

✅ **Progress check:**

- [ ] You can explain in 60 seconds: workflow vs. agent, what tool-calling is, what MCP is for
- [ ] `ollama run llama3.2:3b "hello"` returns text
- [ ] OpenRouter curl returns a valid response
- [ ] `python day1_loop.py` shows both `=== via Anthropic SDK direct ===` and `=== via OpenRouter ===` blocks, each with a tool call and a final answer
- [ ] You can point to the line in `day1_loop.py` where the loop checks for a tool call vs. a final answer
- [ ] You modified `day1_loop.py` to add a second tool and saw it called
- [ ] `aiops-platform/` skeleton committed to GitHub (`aiops-platform` repo)

💡 **Helpful tips:**

- **OpenRouter uses the OpenAI-compatible API.** In Python: `from openai import OpenAI; client = OpenAI(base_url="https://openrouter.ai/api/v1", api_key=os.environ["OPENROUTER_API_KEY"])`.
- **OpenSRE is optional today.** If you're curious about a production AIOps reference, clone and explore. If setup drags past 30 min, skip it — you'll build your own patterns.
- **The two-provider agent is the foundation.** Every agent this sprint inherits this pattern.

---

## Day 2 — Log Triage Agent — Build

🎯 **Goal:** A working CLI agent that reads a real log file and produces a structured Markdown triage report. Three backends: Anthropic SDK, LangChain (`bind_tools`), and Anthropic via OpenRouter. Eval set with 5 cases, at least 3 passing.

📚 **Topic of the day:** Tool design — functions are the agent's hands. Prompt engineering for structured output. Side-by-side comparison of raw SDK vs LangChain abstraction vs OpenRouter API.

📁 **Files already built** (don't re-scaffold — read them first):

| File | Backend | What it does |
|---|---|---|
| `agents/log-intelligence/triage.py` | all | CLI entry point. `--backend anthropic\|langchain\|openrouter` (required). |
| `agents/log-intelligence/planner_anthropic.py` | anthropic | Raw Anthropic SDK loop: manual `stop_reason` checks, budget guard. |
| `agents/log-intelligence/tools_anthropic.py` | anthropic | `Tools._registry` + `dispatch()` in Anthropic tool_use format. |
| `agents/log-intelligence/memory_anthropic.py` | anthropic | `list[dict]` message history in Anthropic message format. |
| `agents/log-intelligence/planner_langchain.py` | langchain | `ChatAnthropic.bind_tools()` + explicit loop. Verbose + LangSmith-traceable. |
| `agents/log-intelligence/planner_openrouter.py` | openrouter | `openai.OpenAI(base_url=openrouter)` — same model via OpenAI-compatible API. |
| `agents/log-intelligence/tools_openrouter.py` | openrouter | Same tool functions, OpenAI function-calling schema format. |
| `agents/log-intelligence/memory_openrouter.py` | openrouter | System prompt as first `{"role":"system"}` message in flat list. |
| `agents/log-intelligence/evaluator.py` | all | Loads `evals/cases.jsonl`, grades, CI exit codes. Backend-agnostic. |
| `agents/log-intelligence/evals/cases.jsonl` | all | 5 labeled HDFS log cases. |
| `agents/log-intelligence/requirements_anthropic.txt` | anthropic | `anthropic`, `pydantic`. |
| `agents/log-intelligence/requirements_langchain.txt` | langchain | `langchain`, `langchain-anthropic`, `langchain-core`, `pydantic`. |
| `agents/log-intelligence/requirements_openrouter.txt` | openrouter | `openai`, `pydantic`. |

⚙️ **Tasks:**

**Setup (one-time):**
- ✅ Pull sample log corpus — `loghub-samples/` already cloned
- 🔲 Create the venv and install Anthropic backend packages:
  ```bash
  cd ~/workspace/claude-code/ai-journey/agentic-ai-projects/aiops-platform/agents/log-intelligence
  uv venv && source .venv/bin/activate
  uv pip install -r requirements_anthropic.txt
  ```
- 🔲 Install LangChain backend packages (same venv):
  ```bash
  uv pip install -r requirements_langchain.txt
  ```
- 🔲 Install OpenRouter backend packages (same venv):
  ```bash
  uv pip install -r requirements_openrouter.txt
  ```

**Run the Anthropic SDK backend:**
- 🔲 Run the agent against the HDFS log:
  ```bash
  cd ~/workspace/claude-code/ai-journey/agentic-ai-projects/aiops-platform/agents/log-intelligence
  source .venv/bin/activate

  python triage.py \
    ~/workspace/claude-code/ai-journey/agentic-ai-projects/aiops-platform/services/ingestion/loghub-samples/HDFS/HDFS_2k.log \
    --backend anthropic
  ```
  Expected: Markdown report with `## Severity`, `## Root Cause Hypothesis`, `## Suggested Actions`.

- 🔲 Read the output. Notice which tools fired (grep, read_log_chunk, cluster_errors). The HDFS log has 80 WARN lines — all DataXceiver exceptions. Expect a P3 severity.

**Run the LangChain backend — same task, different internals:**
- 🔲 Run with `--backend langchain`:
  ```bash
  python triage.py \
    ~/workspace/claude-code/ai-journey/agentic-ai-projects/aiops-platform/services/ingestion/loghub-samples/HDFS/HDFS_2k.log \
    --backend langchain
  ```
  Expected: identical report, plus verbose step output: `[LangChain step N]`, tool call names, and result previews.

- 🔲 Compare the two outputs. Same report structure? Same tool sequence?

**Run the OpenRouter backend — same model, different API path:**
- 🔲 Run with `--backend openrouter`:
  ```bash
  python triage.py \
    ~/workspace/claude-code/ai-journey/agentic-ai-projects/aiops-platform/services/ingestion/loghub-samples/HDFS/HDFS_2k.log \
    --backend openrouter
  ```
  Expected: identical report. The call routes through `openrouter.ai/api/v1` using the OpenAI Python SDK. Check your [OpenRouter dashboard](https://openrouter.ai/activity) — you should see the run with token usage.

**Understand the key difference between the three backends:**

The three planners do the same thing but show different abstractions. Open them side by side:

```
planner_anthropic.py              planner_langchain.py              planner_openrouter.py
─────────────────────────────     ────────────────────────────────  ────────────────────────────────
anthropic.Anthropic()             ChatAnthropic.bind_tools()        openai.OpenAI(base_url=openrouter)
ANTHROPIC_API_KEY                 ANTHROPIC_API_KEY                 OPENROUTER_API_KEY
resp.stop_reason == "tool_use"    response.tool_calls (not empty)   msg.tool_calls (not None/empty)
block.id / block.input            call["id"] / call["args"]         tc.id / json.loads(tc.function.arguments)
input_schema (Anthropic format)   @tool decorator + docstring       function.parameters (OpenAI format)
manual for-loop + stop_reason     manual for-loop + tool_calls      manual for-loop + tool_calls
memory_anthropic.py               LangChain messages list           memory_openrouter.py
```

None of the three is universally "better" — each has trade-offs in transparency, ecosystem, and provider flexibility.

**Run the eval suite:**
- 🔲 Run evals with the Anthropic backend:
  ```bash
  python triage.py --eval --backend anthropic
  ```
  Expected: `Eval: X/5 passed`. Target is 3/5 to pass Day 2.

- 🔲 Run evals with LangChain backend:
  ```bash
  python triage.py --eval --backend langchain
  ```

- 🔲 Run evals with OpenRouter backend:
  ```bash
  python triage.py --eval --backend openrouter
  ```

**Optional — enable LangSmith tracing:**
- 🔲 Sign up at [smith.langchain.com](https://smith.langchain.com) (free tier)
- 🔲 Add to `~/.zshrc`:
  ```bash
  export LANGCHAIN_TRACING_V2=true
  export LANGCHAIN_API_KEY="ls__..."
  export LANGCHAIN_PROJECT="aiops-platform"
  ```
- 🔲 Re-run with LangChain backend. Open smith.langchain.com — you should see a new run with all tool calls, inputs, outputs, and latencies.

**Commit:**
- 🔲 Commit Day 2 work:
  ```bash
  cd ~/workspace/claude-code/ai-journey/agentic-ai-projects/aiops-platform
  git add agents/log-intelligence/ services/ingestion/loghub-samples/
  git commit -m "feat: Day 2 — log triage agent (Anthropic SDK + LangChain + OpenRouter backends)"
  git push
  ```

**Journal:**
- 🔲 Add a Day 2 entry to `aiops-platform/JOURNAL.md`:
  - What the agent got right / wrong on the HDFS log
  - One observation about how LangChain abstracts the loop (vs the raw SDK)
  - One observation about OpenRouter — did the output differ? What did the dashboard show?
  - Any surprise (wrong severity level? missed a WARN cluster?)

✅ **Progress check:**

- [ ] `python triage.py <HDFS_2k.log> --backend anthropic` produces a Markdown report with all 3 sections
- [ ] `python triage.py <HDFS_2k.log> --backend langchain` produces equivalent output (verbose mode)
- [ ] `python triage.py <HDFS_2k.log> --backend openrouter` produces equivalent output (visible in OpenRouter dashboard)
- [ ] `python triage.py --eval --backend anthropic` runs all 5 cases; at least 3 pass
- [ ] You can explain in 30 seconds: how `bind_tools` + explicit loop differs from the raw Anthropic SDK loop
- [ ] You can explain in 30 seconds: what changes between `planner_anthropic.py` and `planner_openrouter.py` (hint: client, key, model string, schema format)
- [ ] `JOURNAL.md` has a Day 2 entry

💡 **Helpful tips:**

- **Tool logic is the same across all three backends.** `grep`, `read_log_chunk`, `cluster_errors` exist in `tools_anthropic.py` (Pydantic + `_registry`), inline in `planner_langchain.py` (`@tool` decorator), and `tools_openrouter.py` (same `_registry`, OpenAI schema). Same logic, different wiring.
- **If the LangChain output looks wrong, check the docstrings.** In LangChain, the `@tool` function's docstring IS the tool description the LLM reads. Vague docstring = confused LLM.
- **OpenRouter model swap = one string.** Change `model` in `OpenRouterPlannerConfig` to `"openai/gpt-4o-mini"` and rerun — no other code changes. This is the Day 3 experiment foundation.
- **Treat log content as adversarial.** Logs can contain `"ignore previous instructions"`. The system prompt has a guard for this — don't remove it.
- **When output is wrong, change the prompt before changing the code.** 80% of bugs at this stage are prompt issues.
- **LangChain verbose=True is your friend.** It shows the full Reason→Act→Observe chain. Use it when debugging why the agent made a wrong tool call.

---

## Day 3 — Log Triage — Model Routing Experiment

🎯 **Goal:** Run the multi-model comparison experiment. Commit `experiments/log-triage-model-routing.md` with real numbers across three providers. Fill in the README senior-signal sections. You'll have data — not opinions — about which model to use for log triage.

📚 **Topic of the day:** Model routing as an engineering decision. Cost-per-run as a first-class metric. The difference between "it works" and "it's the right tool for the job."

> ✅ **Eval already at 100% (5/5)** from Day 2 — prompt tuning step is done.

📁 **Files already built** (don't re-scaffold):

| File | What it does |
|---|---|
| `agents/log-intelligence/run_experiment.py` | Runs 5 eval cases × 3 models, captures timing + tokens, writes Markdown report. |
| `agents/log-intelligence/evaluator.py` | Updated with real `time.perf_counter()` timing and latency stats in output. |
| `agents/log-intelligence/triage.py` | Now has `--model` flag to override the OpenRouter model string without editing code. |
| `agents/log-intelligence/planner_openrouter.py` | Now tracks `agent.usage` (input/output tokens) per run. |
| `experiments/` | Output directory for the report. |

⚙️ **Tasks:**

**Smoke test (do this first — 1 case per model, ~30 seconds):**
- 🔲 Confirm the experiment runner is wired up:
  ```bash
  cd ~/workspace/claude-code/ai-journey/agentic-ai-projects/aiops-platform/agents/log-intelligence
  source .venv/bin/activate
  python run_experiment.py --quick
  ```
  Expected: three model blocks in stdout (`Claude Sonnet 4.6`, `Claude Haiku 4.5`, `GPT-4o Mini`), each showing 1 case result with latency and token counts. A report file is written to `experiments/`.

**Run the full experiment (3 models × 5 cases):**
- 🔲 Run the full experiment:
  ```bash
  python run_experiment.py
  ```
  This runs 15 cases total (3 models × 5 cases), with a 3-second sleep between cases per model to avoid rate limits. Total runtime: ~5–10 minutes depending on latency.

  Expected stdout summary:
  ```
  ▶  Claude Sonnet 4.6  (anthropic/claude-sonnet-4-6)
      [1/5] case-001 ... ✓  3.2s  in=1842 out=312
      ...
  ▶  Claude Haiku 4.5  (anthropic/claude-haiku-4-5)
      ...
  ▶  GPT-4o Mini  (openai/gpt-4o-mini)
      ...

  ✅  Report written to: .../experiments/log-triage-model-routing.md
  ```

**If you hit 402 (insufficient credits):**
  ```bash
  # Sonnet is expensive — run Haiku + GPT-4o-mini only to conserve credits
  python triage.py --eval --backend openrouter --model anthropic/claude-haiku-4-5
  python triage.py --eval --backend openrouter --model openai/gpt-4o-mini
  # Then fill in the Sonnet row manually with estimated numbers
  ```

**Triage outputs are saved automatically by `run_experiment.py`:**

You do not need separate `triage.py` commands to get outputs for qualitative review. After `run_experiment.py` finishes, each model's full triage text is written to `experiments/outputs/`:
```
experiments/outputs/
  anthropic-claude-sonnet-4-6.md
  anthropic-claude-haiku-4-5.md
  openai-gpt-4o-mini.md
```
Open these files directly in your editor to review and compare the outputs side-by-side.

**Set a shell variable for shorter commands below:**
```bash
EXP=~/workspace/claude-code/ai-journey/agentic-ai-projects/aiops-platform/experiments/outputs
```

**Verify structured output format — run this check for each model:**
- 🔲 Confirm all 3 required sections are present (should return `3` for each):
  ```bash
  grep -c "^## Severity\|^## Root Cause Hypothesis\|^## Suggested Actions" \
      "$EXP/anthropic-claude-sonnet-4-6.md"
  grep -c "^## Severity\|^## Root Cause Hypothesis\|^## Suggested Actions" \
      "$EXP/anthropic-claude-haiku-4-5.md"
  grep -c "^## Severity\|^## Root Cause Hypothesis\|^## Suggested Actions" \
      "$EXP/openai-gpt-4o-mini.md"
  ```
  Anything less than `3` = missing section = production failure regardless of eval pass rate.

- 🔲 Read each file and check the following for every section:

  **`## Severity`** — must have:
  - Exactly `P1`, `P2`, `P3`, or `P4` (not "High", "moderate", "critical" — those are format failures)
  - One-line justification after the P-level

  **`## Root Cause Hypothesis`** — must have:
  - At least one specific log line citation with a timestamp, e.g. `081109 203518 ... DataXceiver`
  - A ranked list if multiple hypotheses
  - If it says "there appear to be network issues" with no log citations → quality failure

  **`## Suggested Actions`** — must have:
  - Numbered list (not bullets)
  - Specific component names (e.g. "check DataXceiver thread pool", not "investigate the errors")
  - At least 3 concrete steps

**Interpret token counts before drawing conclusions:**
- 🔲 Compare the `in=` token counts from the experiment run. A model using **far fewer input tokens** than the others likely made fewer tool calls or stopped reading logs early — it's cheaper because it did *less*, not because it was more efficient. Verify by checking if the report cites actual log lines.
  ```bash
  # Count how many log-line citations (timestamps) appear in each report
  grep -c "^[0-9]\{6\} [0-9]\{6\}" "$EXP/anthropic-claude-sonnet-4-6.md"   # HDFS timestamp format
  grep -c "^[0-9]\{6\} [0-9]\{6\}" "$EXP/anthropic-claude-haiku-4-5.md"
  grep -c "^[0-9]\{6\} [0-9]\{6\}" "$EXP/openai-gpt-4o-mini.md"
  # Zero citations = the model didn't read the log deeply = not production-ready
  ```

**Run the full 5-case eval per model (not just --quick):**
- 🔲 Run the full eval for each model to surface failure modes across multiple cases:
  ```bash
  python triage.py --eval --backend openrouter --model anthropic/claude-sonnet-4-6
  python triage.py --eval --backend openrouter --model anthropic/claude-haiku-4-5
  python triage.py --eval --backend openrouter --model openai/gpt-4o-mini
  ```
  Watch for patterns across the 5 cases — a model may pass the `contains` rubric on most cases but still have quality issues. Note which cases FAIL and why.

**Identify notable failure modes — what to look for:**

| Failure mode | How to detect it |
|---|---|
| Missing sections | `grep -c "^## "` returns < 3 |
| Header format drift | Model writes `# Severity` or `**Severity**` instead of `## Severity` — passes a human read but breaks tooling |
| No log line citations | Section `## Root Cause Hypothesis` has no timestamps — generic statements only |
| Generic suggested actions | Actions say "check the logs" / "restart the service" — no specific component, command, or metric named |
| Truncated output | Report cuts off mid-sentence — check if `out=` token count is near the `max_tokens` limit |
| Skipped tool calls | Model answered without calling `read_log_chunk` / `grep` / `cluster_errors` — visible from low `in=` token count |
| Severity label non-standard | Uses "High" / "Low" / "Warning" instead of P1–P4 |

**Fill in qualitative observations and recommendation:**
- 🔲 Open `experiments/log-triage-model-routing.md` and fill in `## Qualitative observations` for each model using what you found above:
  - Output quality: (Excellent / Good / Acceptable / Poor)
  - Followed structured output format: (Yes / Partial — note which sections failed)
  - Notable failure modes: (list what you observed, or "None observed across 5 cases")
- 🔲 Fill in `## Recommendation`:
  - Which model for **production** (quality-sensitive, on-call SRE reads this)?
  - Which model for **dev iteration** (cost-optimised, you're tuning prompts)?
  - Routing strategy — e.g. "Run Haiku on all logs; if severity is P1/P2, re-run with Sonnet for a second opinion"

**Verify cost is within budget:**
- 🔲 Confirm from the report that Haiku avg $/run < $0.05 for the HDFS log.
- 🔲 Cross-check against [openrouter.ai/activity](https://openrouter.ai/activity) — the dashboard shows actual spend per request, which lets you verify your token-count-based estimate is accurate.

**Fill in README senior-signal sections:**
- 🔲 Open `agents/log-intelligence/README.md` and fill in using `_templates/PROJECT_README_TEMPLATE.md`:
  - **Problem Statement** — one paragraph: what problem does the agent solve, what is the baseline MTTD without it, what does the agent achieve
  - **SRE Metrics** — populate the table with real numbers from today's eval and experiment (latency p50/p95, pass rate, $/run per model)
  - **Failure Modes** — at least 4 rows drawn from what you observed above: e.g. missing sections, no log citations, severity label drift, prompt injection via log lines

**Commit:**
- 🔲 Commit Day 3 work:
  ```bash
  cd ~/workspace/claude-code/ai-journey/agentic-ai-projects/aiops-platform
  git add agents/log-intelligence/ experiments/
  git commit -m "feat: Day 3 — model routing experiment (Sonnet vs Haiku vs GPT-4o-mini)"
  git push
  ```

**Journal:**
- 🔲 Add a Day 3 entry to `aiops-platform/JOURNAL.md`:
  - Which model surprised you (better or worse than expected)?
  - What's your routing strategy going forward?
  - Cost delta between cheapest and most expensive model on this task

✅ **Progress check:**

- [ ] `python run_experiment.py --quick` completes without errors for all 3 models
- [ ] `python run_experiment.py` (full run) completes — report written to `experiments/`
- [ ] `grep -c "^## "` returns `3` for each model's output (all sections present)
- [ ] Each model's `## Severity` section uses P1/P2/P3/P4 — not freeform severity labels
- [ ] Each model's `## Root Cause Hypothesis` cites at least one actual log line with a timestamp
- [ ] Full 5-case eval run for each model — pass rates recorded in the report
- [ ] `experiments/log-triage-model-routing.md` has real pass-rate, latency, token count, and cost numbers
- [ ] Qualitative observations filled in for all 3 models (format, citations, failure modes)
- [ ] Recommendation section has a concrete routing decision with cost/quality reasoning
- [ ] Haiku avg $/run < $0.05 verified in report and cross-checked against openrouter.ai/activity
- [ ] README has Problem Statement, SRE Metrics (with real numbers from today), and Failure Modes filled in
- [ ] Day 3 committed to GitHub

💡 **Helpful tips:**

- **Fewer input tokens ≠ better.** If one model uses 7× fewer tokens than the others, it likely skipped tool calls or stopped reading early. Always verify with `grep -c "^[0-9]"` on the output to count log citations.
- **Cheap + fast is only better if quality is equivalent.** Check all three criteria: sections present, P-level classification, log line citations. A report that passes the `contains` eval rubric but has no citations is not production-ready.
- **Don't cherry-pick results.** Honest numbers where a cheaper model underperforms are *more* impressive than fake parity — they show you actually read the output.
- **The `--model` flag lets you test any OpenRouter model** without touching code:
  ```bash
  python triage.py $LOG --backend openrouter --model mistralai/mistral-7b-instruct
  ```
  Browse [openrouter.ai/models](https://openrouter.ai/models) for current model strings and prices.
- **Rate limits:** if you see 429 errors, increase `--sleep`:
  ```bash
  python run_experiment.py --sleep 5
  ```
- **Costs are cumulative across tool calls.** The agent calls tools 3–5 times per triage. Token counts in the report are the *total* across all steps in a run, not a single API call.

---

## Day 4 — PR Security Reviewer (DevSecOps Anchor)

🎯 **Goal:** A GitHub Action at `aiops-platform/agents/pr-reviewer/` that posts a structured security review on a real PR. Idempotent (no spam on rebuild).

📚 **Topic of the day:** Webhooks. Idempotent automation. CI integration. The DevSecOps signal.

⚙️ **Tasks:**

- 🔲 In `~/workspace/claude-code/ai-journey/agentic-ai-projects/aiops-platform/agents/pr-reviewer/`: LangChain agent with PR-fetch + Semgrep tools
- 🔲 Tools: `fetch_pr_diff(repo, number)` (PyGithub), `run_semgrep(rules)`, `post_review_comment(body)` with idempotency tag `<!-- ai-reviewer:v1 -->`
- 🔲 Output schema: list of `{file, line, severity, cwe_id, explanation, suggested_fix}`
- 🔲 Wrap as `.github/workflows/ai-review.yml` triggered on `pull_request`
- 🔲 Test on a deliberately-bad PR (hardcoded secret, eval injection, SQL-string concatenation)
- 🔲 README: senior-signal sections + screenshot of the bot comment

✅ **Progress check:**

- [ ] Open a fresh PR; bot comments within 60s citing at least one CWE
- [ ] Push another commit; bot updates its comment, doesn't duplicate
- [ ] When `GITHUB_TOKEN` is wrong, the action fails loud with a clear error
- [ ] README "Failure Modes" lists at least 5 real failure modes

💡 **Helpful tips:**

- **Test failure paths today.** What if Semgrep returns 200 findings? What if the PR has no code changes?
- **The bot is a *security* reviewer.** Style, perf, naming — not its job.
- **Via OpenRouter you can test the same PR review with GPT-4o** — useful to catch cases where one model misses something.

---

## Day 5 — Slack Incident Bot + Observability Layer

🎯 **Goal:** Bot receives an alert, posts a Block Kit incident card to Slack within 30s. LangSmith traces are flowing. Four Prometheus metrics are exposed on `/metrics`.

📚 **Topic of the day:** Long-running agent processes. Two-layer observability — LangSmith for trace-level debugging, Prometheus for aggregate metrics and alerting. Why both matter and what each one tells you.

⚙️ **Tasks:**

- ✅ `agents/slack-incident-bot/` — Slack Bolt app (Socket Mode), Anthropic ReAct agent
- ✅ `planner.py` — ReAct loop: `get_alert_context` → `post_incident_card` → `end_turn`
- ✅ `tracing.py` — LangSmith layer: `wrap_anthropic()` + `@ls_traceable` on `handle_alert`
- ✅ `metrics.py` — Prometheus layer: Counter/Histogram for requests, duration, tokens, iterations
- ✅ `bot.py` — starts `start_metrics_server()` at startup; metrics on `http://localhost:8000/metrics`
- 🔲 Run `make setup-slack-bot` to install `prometheus-client` (now in `requirements.txt`)
- 🔲 Set `METRICS_ENABLED=true` and `METRICS_PORT=8000` in `.env`
- 🔲 Fire a test alert and verify metrics: `python bot.py --trigger ALERT-001`
- 🔲 `curl http://localhost:8000/metrics | grep incident_bot` — confirm 4 metric families
- 🔲 Open LangSmith → project `slack-incident-bot` → confirm trace tree is present
- 🔲 Read the trace — note one surprise in `JOURNAL.md`

✅ **Progress check:**

- [ ] `make test-slack-bot` passes (34 tests: 23 original + 11 metrics tests)
- [ ] Bot starts and logs `Prometheus metrics available at http://localhost:8000/metrics`
- [ ] `curl http://localhost:8000/metrics | grep incident_bot` returns all 4 metric families:
  - `incident_bot_requests_total`
  - `incident_bot_duration_seconds`
  - `incident_bot_tokens_total`
  - `incident_bot_iterations_total`
- [ ] LangSmith shows `incident_planner.handle_alert` chain with 2 nested LLM runs
- [ ] You can read the token count from LangSmith and cross-check with `incident_bot_tokens_total`

💡 **Helpful tips:**

- **`prometheus_client` starts a background thread** — `start_http_server()` is non-blocking, so it doesn't interfere with the Socket Mode event loop.
- **Metrics survive across alerts.** The Counter values accumulate for the lifetime of the process — that's intentional. Use `rate()` in PromQL to get per-second rates.
- **Slack Bolt's socket mode is the fastest local-dev path.** No webhooks, no ngrok.
- **Disable metrics in tests** by setting `METRICS_ENABLED=false` or not setting `METRICS_ENABLED` — the module degrades gracefully and tests pass either way.

---

## Day 6 — K8s Doctor Foundation (LangGraph)

🎯 **Goal:** A working `aiops-platform/agents/k8s-doctor/` that diagnoses a CrashLoopBackOff in your local kind cluster. Clean LangGraph state machine — your own design.

📚 **Topic of the day:** LangGraph state machines. Building your first MCP server. State-shape-first design thinking.

⚙️ **Tasks:**

- 🔲 `kind create cluster --name doctor-lab`
- 🔲 Deploy two deliberately-broken workloads (CrashLoopBackOff + ImagePullBackOff)
- 🔲 In `~/workspace/claude-code/ai-journey/agentic-ai-projects/aiops-platform/agents/k8s-doctor/`: structure = `src/agents`, `src/tools`, `src/graph`
- 🔲 LangGraph state: `{ symptom, observations[], hypotheses[], next_action, model_used }`
  - Note `model_used` — you'll route different tasks to different models on Day 7
- 🔲 Tools: `kubectl_describe`, `kubectl_logs`, `kubectl_events`, `prom_query`
- 🔲 Build a Prometheus MCP server in `~/workspace/claude-code/ai-journey/agentic-ai-projects/aiops-platform/services/mcp-prometheus/`. Start with one query: `up`.
- 🔲 Wire LangGraph: `observe → hypothesize → propose`. Run against the broken deployment.

✅ **Progress check:**

- [ ] Agent diagnoses CrashLoopBackOff in <2 min
- [ ] MCP server is callable via `mcp` client
- [ ] LangGraph graph has at least 3 nodes with clear state transitions
- [ ] LangSmith trace shows the full pipeline

💡 **Helpful tips:**

- **Design the state shape on paper before writing code.** State shape is the contract — get it wrong and you'll refactor everything.
- **Test in `--dry-run` mode all day.** Build the muscle of read-only-by-default.
- **Keep [LangGraph "Build an Agent"](https://langchain-ai.github.io/langgraph/tutorials/introduction/) open in a tab** — reference constantly.

---

## Day 7 — K8s Doctor Polish + Multi-Model Routing (+ Optional: OpenSRE PR)

🎯 **Goal:** K8s Doctor handles 3+ failure modes with `--apply` gate. Model routing strategy implemented and numbers published. Optionally: an OpenSRE PR submitted upstream.

📚 **Topic of the day:** Iterative agent improvement. **Model routing as an engineering decision.** Open-source contribution as a portfolio signal.

⚙️ **Tasks:**

- 🔲 Add OOMKilled scenario; verify diagnosis
- 🔲 Add `--apply` flag with explicit human y/n approval gate
- 🔲 5 eval cases in `~/workspace/claude-code/ai-journey/agentic-ai-projects/aiops-platform/agents/k8s-doctor/evals/cases.jsonl`; aim ≥80% pass
- 🔲 Fill in K8s Doctor README senior-signal sections using `~/workspace/claude-code/ai-journey/agentic-ai-projects/_templates/PROJECT_README_TEMPLATE.md`
- 🔲 **Model routing implementation:** update `src/graph` to route by node type:
  - `observe` node → `anthropic/claude-haiku-4-5` (cheap, deterministic kubectl reads)
  - `hypothesize` node → `anthropic/claude-sonnet-4-6` (complex reasoning)
  - `propose` node → `anthropic/claude-sonnet-4-6` (high-stakes remediation output)
- 🔲 Run the same 5 eval cases with routing ON vs. routing OFF (Sonnet everywhere)
- 🔲 Publish in `~/workspace/claude-code/ai-journey/agentic-ai-projects/aiops-platform/experiments/k8s-doctor-model-routing.md`:
  - Pass rate, $/run, latency delta — routed vs. unrouted
  - Recommendation with reasoning

**⭐ Optional — OpenSRE PR (high-signal, not a blocker):**

- 🔲 Browse [Tracer-Cloud/opensre/issues](https://github.com/Tracer-Cloud/opensre/issues) — look for `good-first-issue` or doc improvements
- 🔲 Comment on the issue ("I'd like to take this"); fork; branch; implement
- 🔲 Submit the PR — even a doc fix counts
- 🔲 If merged or reviewed: link it from your K8s Doctor README ("Contributed to OpenSRE: PR #N")

> **Why bother?** A single merged PR to a production AIOps repo is a stronger signal than three solo repos. It proves you can read, adapt, and contribute to someone else's production codebase. If Day 7 runs long, skip it — but if you have headroom, this is the highest-leverage bonus task in the sprint.

✅ **Progress check:**

- [ ] 3 different failure modes diagnosed correctly across 5+ runs each
- [ ] `--apply` blocks until y/n; refuses in non-interactive contexts
- [ ] Eval pass rate ≥80%
- [ ] `experiments/k8s-doctor-model-routing.md` published with real numbers
- [ ] K8s Doctor README is complete
- [ ] (Optional) OpenSRE PR submitted

💡 **Helpful tips:**

- **Model routing is a senior engineering decision, not a hack.** Your `experiments/` doc is the proof.
- **The routing savings will surprise you.** `observe` runs 10–20× per session; routing it to Haiku pays back fast.
- **For the OpenSRE PR:** a 10-line doc improvement submitted cleanly beats a 300-line feature left in draft.

---

## Day 8 — SAST Auto-Fixer + IaC Generator (Combined)

🎯 **Goal:** One passing auto-PR for a SAST finding. A working NL → Terraform generator passing 2 of 3 test prompts. OpenRouter used for cheap IaC iteration.

📚 **Topic of the day:** Long-horizon agent tasks. Code-edit agents. Sandboxed execution. Iterative self-correction (generate → validate → repair).

⚙️ **Tasks:**

**Morning — SAST Auto-Fixer (`aiops-platform/agents/sast-auto-fix/`):**

- 🔲 Clone OWASP WebGoat as test target:
  ```bash
  git clone https://github.com/WebGoat/WebGoat \
    ~/workspace/claude-code/ai-journey/agentic-ai-projects/aiops-platform/agents/sast-auto-fix/targets/WebGoat
  ```
- 🔲 LangGraph agent with tools: `clone_repo`, `run_semgrep`, `read_file`, `write_file`, `git_diff`, `run_tests_in_docker` (sandboxed: `--network=none`), `open_pr`
- 🔲 Loop: scan → pick top finding → generate fix → run tests in sandbox → if pass, commit; if not, retry up to 2×
- 🔲 Verify on at least 1 finding that lands a clean PR

**Afternoon — IaC Generator (`aiops-platform/agents/iac-generator/`):**

- 🔲 FastAPI service; `uv pip install voyageai chromadb langchain-ollama`
- 🔲 Index 10–20 Terraform AWS module READMEs into Chroma (Voyage embeddings)
- 🔲 LangChain agent with **two backends via OpenRouter**:
  - `anthropic/claude-sonnet-4-6` for production-quality output
  - `openai/gpt-4o-mini` or `mistralai/mistral-7b-instruct` for cheap dev iteration
- 🔲 Tools: `retrieve_module_docs`, `terraform_validate`, `checkov_scan`, `write_file`
- 🔲 Loop: generate → validate → repair (max 5)
- 🔲 Test 3 prompts: simple S3 bucket, 3-tier app, VPC with peering

✅ **Progress check:**

- [ ] SAST agent opens a real PR with passing tests
- [ ] Sandbox is verifiably isolated (`curl example.com` inside container fails)
- [ ] IaC agent (Sonnet): 2 of 3 prompts produce `terraform validate`-clean output
- [ ] IaC agent (cheap model via OpenRouter): completes the same loop — slower/lower quality is fine

💡 **Helpful tips:**

- **Code-edit is hard.** Cap `MAX_STEPS=8`; feel the limitation.
- **Use `git diff` as a tool, not `read_file → modify → write_file`.** The diff is the artifact.
- **Cheap model iteration via OpenRouter is the right move for IaC.** You'll regenerate Terraform 50× tuning prompts. Routing to `gpt-4o-mini` costs ~10× less per call than Sonnet.

---

## Day 9 — Alert Correlator + Multi-Agent SRE Team Start (CrewAI)

🎯 **Goal:** Synthetic alert stream produces clustered incident docs with confidence scores. Four CrewAI specialist agents defined; orchestrator runs one incident through and the LangSmith trace is clean.

📚 **Topic of the day:** Hybrid retrieval (time + semantic). Multi-agent orchestration. Reading every trace as a habit.

⚙️ **Tasks:**

**Morning — Alert Correlator (`aiops-platform/agents/alert-correlator/`):**

- 🔲 `docker run -d --name pgvector -p 5432:5432 -e POSTGRES_PASSWORD=pw pgvector/pgvector:pg16`
- 🔲 Synthetic alert generator: emits Prometheus AlertManager-format alerts at varying rates
- 🔲 Embed each alert (Voyage AI); store in pgvector with `(timestamp, service, embedding)`
- 🔲 LangGraph correlation: on each new alert, find similar in last 15 min → cluster → emit JSON incident doc

**Afternoon — Incident Commander (`aiops-platform/agents/incident-commander/`):**

- 🔲 `uv pip install crewai crewai-tools`
- 🔲 Define 4 agents (Triage, Investigator, Mitigator, Communicator) with role/goal/backstory
- 🔲 Orchestrator: triage → parallel(investigate, communicate) → mitigate
- 🔲 Wire your existing tools (kubectl from K8s Doctor, log triage from Day 2) as CrewAI tools
- 🔲 Run against ONE incident (`high-error-rate-checkout`); read the LangSmith trace
- 🔲 Log $/incident — the CrewAI multi-agent cost will surprise you

✅ **Progress check:**

- [ ] Alert correlator clusters synthetic alerts; confidence scores look directionally right
- [ ] LangSmith trace shows all 4 CrewAI agents with clear handoffs
- [ ] You can explain *why* Investigator and Communicator ran in parallel
- [ ] Total $/incident logged and < $0.50

💡 **Helpful tips:**

- **CrewAI's `verbose=True` is your friend today.**
- **Consider routing the Communicator agent to a cheaper model** — it writes Slack summaries, not diagnoses. One-line change via OpenRouter.
- **pgvector is faster than Chroma at this volume.**

---

## Day 10 — Multi-Agent Finish + Pentest Agent (Lab)

🎯 **Goal:** Multi-agent system handles 3 distinct incidents end-to-end with approval gates. Pentest agent finds at least 1 valid CVE in an isolated lab target.

📚 **Topic of the day:** Approval gates as primary safety. Offensive tooling safety. Long-horizon planning under uncertainty.

⚙️ **Tasks:**

**Morning — Incident Commander finish:**

- 🔲 Add approval gate: Slack interactive message (or CLI prompt for solo dev)
- 🔲 Run multi-agent against 3 scenarios (high error rate, slow latency, OOM)
- 🔲 Add Failure Modes section (use `~/workspace/claude-code/ai-journey/agentic-ai-projects/aiops-platform/docs/postmortems/incident-001.md` as inspiration)
- 🔲 Cost guard: orchestrator halts if total spend > $1.00/incident

**Afternoon — Pentest Agent (`aiops-platform/agents/pentest-lab/`):**

- 🔲 `docker network create --internal pentest-lab` — `--internal` means NO internet egress
- 🔲 `docker run --rm -d --network pentest-lab --name target vulhub/struts2-s2-053`
- 🔲 **Write the scope guard FIRST.** Every tool call validates target IP ∈ `ALLOWED_NETS`. Test it explicitly.
- 🔲 LangGraph agent with tools: `nmap_scan`, `nuclei_scan`, `dir_brute`, `try_exploit`, `loot_grab`
- 🔲 Add a "reflection" node: every 5 actions, re-evaluate strategy
- 🔲 Run; capture results in `~/workspace/claude-code/ai-journey/agentic-ai-projects/aiops-platform/docs/pentest-report-001.md`
- 🔲 README ethics gate prominently displayed at the top (lab-only, owned-targets-only)

✅ **Progress check:**

- [ ] Multi-agent system handles 3 incidents; LangSmith trace clean
- [ ] Scope guard refuses out-of-scope targets with a *clear error*, not silently
- [ ] Pentest agent finds at least 1 valid CVE on the lab target
- [ ] Pentest report committed

💡 **Helpful tips:**

- **The scope guard test is critical. Write the test FIRST.**
- **The approval gate is the most important code in your platform.** Write tests, document the contract.
- **Pentest agent ethics:** lab-only, owned targets only — loud README banner.

---

## Day 11 — Demos + Micro-SaaS Scaffold + Multi-Provider Comparison (Senior-Signal Day)

🎯 **Goal:** Three flagship demo gifs. Micro-SaaS skeleton live. Multi-provider comparison experiment published — the artifact that signals senior cost-aware thinking.

📚 **Topic of the day:** Closing the loop. Productization. Telling the story. *Experiments as portfolio artifacts.*

⚙️ **Tasks:**

**Morning — Demos:**

- 🔲 `brew install asciinema vhs`
- 🔲 Record 3 demo gifs:
  1. Log Triage agent on a real log file (Day 2–3 work)
  2. K8s Doctor diagnosing a broken pod (Day 6–7 work)
  3. Multi-Agent Incident Commander handling a synthetic incident (Day 9–10 work)
- 🔲 Embed gifs at the top of each agent's README

**Afternoon — Micro-SaaS scaffold:**

- 🔲 Create Next.js frontend:
  ```bash
  npx create-next-app@latest \
    ~/workspace/claude-code/ai-journey/agentic-ai-projects/aiops-platform/saas/web \
    --typescript --tailwind --app
  ```
- 🔲 FastAPI backend at `aiops-platform/saas/api/` wraps the IaC Generator
- 🔲 Stub endpoints: `POST /runs` (SSE), `GET /runs/:id`, `GET /healthz`
- 🔲 Stub auth (Supabase) and billing (Stripe metered) — leave clear `TODO` markers
- 🔲 Architecture diagram in `aiops-platform/saas/README.md`

**Evening — The multi-provider comparison (the senior signal):**

- 🔲 In `~/workspace/claude-code/ai-journey/agentic-ai-projects/aiops-platform/experiments/multi-provider-comparison.md`: run the Day-2 log triage agent over the same 5 eval cases with **5 backends via OpenRouter**:
  - `anthropic/claude-sonnet-4-6`
  - `anthropic/claude-haiku-4-5`
  - `openai/gpt-4o-mini`
  - `mistralai/mistral-7b-instruct`
  - `meta-llama/llama-3.1-70b-instruct`
- 🔲 Report per model: eval pass rate, p50/p95 latency, $/run, qualitative observations
- 🔲 Recommendation section: "For production log triage, use X. For development iteration, use Y. Here's why."

**Late evening — Publish (use [`GITHUB_SETUP.md`](../GITHUB_SETUP.md) §13 as checklist):**

- 🔲 Run through the Day-11 publish checklist in `GITHUB_SETUP.md`
- 🔲 Flip repo from private → public
- 🔲 Tag `v0.1.0`; draft GitHub Release notes
- 🔲 Update profile README; pin the repo
- 🔲 Draft LinkedIn post (sleep on it; publish Day 12 morning)
- 🔲 Cross off Phase 1 ✅ in `AGENTIC_AI_ROADMAP.md`

✅ **Progress check:**

- [ ] Three flagship gifs visible in their READMEs
- [ ] `saas/web/` and `saas/api/` exist with clean architecture doc
- [ ] `experiments/multi-provider-comparison.md` published with real numbers across 5 models and a clear recommendation
- [ ] Phase 1 officially DONE

💡 **Helpful tips:**

- **Get the gifs done first.** They're 80% of how others perceive your work.
- **The 5-model comparison is significantly more valuable than the original Ollama-vs-Sonnet plan.** The cross-provider table is the kind of thing that gets shared.
- **Take the weekend off after Day 11.** Burnout kills polish.

---

## After Day 11: The Compounders

1. **One blog post per flagship.** Cross-post LinkedIn + dev.to. The multi-provider comparison is already a post on its own.
2. **OpenSRE follow-up PR (if you didn't do it on Day 7).** A second PR, or a first one if Day 7 ran long. The compound interest on open-source contributions is real.
3. **One conference proposal.** SREcon, KubeCon, DevOpsDays. Submit even if you don't expect acceptance.
4. **Phase 2:** Wire real Stripe billing into the SaaS, ship one paying customer, write the launch post.

---

## Cross-cutting practices (every day)

- **Commit often.** End-of-day minimum.
- **Read at least one LangSmith trace per day.** Pattern recognition compounds.
- **Append `<date> <agent> <model> <$cost>` to `aiops-platform/costs.txt` daily.** By Day 11 you'll have real $/run intuition — and the data to back up your routing decisions.
- **One sentence per day in `aiops-platform/JOURNAL.md`** — what worked / what didn't / surprise.

---

## Slip recovery

| Pattern | Recovery |
|---|---|
| Day 1 toolchain setup drags | Prioritise: API keys + first loop. Docker/k8s can wait until Day 6. |
| Day 6 LangGraph confusion | Build the minimal LangGraph tutorial agent first; apply the pattern to K8s Doctor after. |
| Day 7 OpenSRE PR blocks you | Skip it entirely — it's optional. Move on. |
| Day 8 SAST or IaC blocks | Time-box each to 4 hours; the one unfinished moves to Day 9 morning. |
| Day 9 multi-agent overwhelms | Run a single-agent baseline for the same incident first; the contrast teaches more. |
| Falling 1+ day behind | Drop the Pentest Agent (Day 10 afternoon) before dropping anything else. |

---

## What you'll have at the end of Day 11

- **One platform repo** (`aiops-platform/`) with 8 working agents, observability, infra scaffolding, postmortem, runbook
- **Three demo gifs** for the flagships
- **Two routing experiments** in `experiments/` — one per-agent, one multi-provider
- **One micro-SaaS skeleton** ready for Phase 2
- **Eval sets across all agents**, ≥80% pass rate
- **A trail of LangSmith traces** documenting every decision your agents made
- **Provider-agnostic agent design** that works with Anthropic, OpenAI, Mistral, or Llama via a single config change
- **(Optionally) One submitted OpenSRE PR** — the highest-signal bonus credential of the sprint

That's the senior-signal portfolio. Now go build.

---

*Schedule v3 compiled: 2026-04-29. Previous version at [`SCHEDULE-v1.md`](SCHEDULE-v1.md).*
