# SETUP.md — Tools, Installs & Repos

> **What this is:** Strictly installation, configuration, and account setup. Run through this *before* starting any day in [`SCHEDULE.md`](SCHEDULE.md).
>
> **What this is NOT:** A daily schedule, learning content, or implementation steps. Those all live in [`SCHEDULE.md`](SCHEDULE.md).
>
> **How it's organized:** by day, because some installs only matter on certain days (e.g., `pgvector` is only needed Day 9). You can install everything Day 1, or install just-in-time. Either works.
>
> **Companion files:**
> - [`SCHEDULE.md`](SCHEDULE.md) — daily build plan with implementation steps
> - [`Makefile`](../Makefile) — all common dev tasks; run `make` to see available targets
> - [`GITHUB_SETUP.md`](../GITHUB_SETUP.md) — publishing the platform repo (Day 11)
>
> Living document. Update checkboxes as you go. Add notes/errors under each section.
> Last updated: 2026-05-09 (Day 5 — Slack bot + LangSmith observability; Makefile added)

---

## How to use this file

- `🔲` = not started · `🔄` = in progress · `✅` = done · `❌` = blocked/skipped (add note)
- Run commands exactly as written unless a note says otherwise.
- Add inline notes for any version mismatches, workarounds, or surprises — future-you will thank present-you.

---

## Makefile quick-reference

All common dev tasks are wired into the top-level `Makefile`. Run `make` (bare) to list targets.

| Command | What it does |
|---|---|
| `make setup` | Bootstrap ALL agent venvs (run once after clone) |
| `make setup-log` | Bootstrap `log-intelligence` venv only |
| `make setup-bot` | Bootstrap `slack-incident-bot` venv only |
| `make test` | Run all unit tests (all agents) |
| `make test-log` | Run `log-intelligence` tests only |
| `make test-bot` | Run `slack-incident-bot` tests only (34 tests) |
| `make eval` | Run agent eval suite (Anthropic backend, 80% threshold) |
| `make eval BACKEND=langchain` | Run eval with LangChain backend |
| `make eval THRESHOLD=1.0` | Require 100% pass rate |
| `make lint` | Ruff lint + format check |
| `make fmt` | Auto-fix lint + format |

> **Why Make?** Each agent has its own isolated venv. The Makefile manages the full lifecycle — create, install, test, lint — in one place so docs and CI always stay in sync. Every doc in this repo references `make <target>` rather than raw `uv` / `pytest` commands. See [README.md](README.md) for the full rationale.

---

## Day 1 — Core Toolchain + OpenSRE

### Python & Node runtime

```bash
# Pick pyenv (preferred over brew python@3.11 — avoids version conflicts)
brew install pyenv uv node

pyenv install 3.11
pyenv global 3.11

# Verify
python --version   # should show 3.11.x
node --version
uv --version
```

- ✅ `pyenv` installed
- ✅  Python 3.11 set as global
- ✅  `uv` installed
- ✅  `node` installed

> **Note:** Do NOT also install `brew python@3.11` — pick pyenv or brew, not both.

---

### Ollama (local model runtime)

```bash
# Install via official installer (not brew — avoids permission issues)
# https://ollama.ai/download → macOS .dmg

# After install, pull the working model for your RAM:
ollama pull llama3.2:3b       # <16GB RAM — fast, good enough for iteration
# ollama pull llama3.1:8b     # 16GB RAM — better reasoning, slower
# llama3.3:70b requires 64GB+ — skip it

# Verify
ollama run llama3.2:3b "hello"
```

- 🔲 Ollama installed
- 🔲 Model pulled and responding

> **RAM guide:** 3b = 4–8GB · 8b = 8–16GB · 70b = 64GB+ (cloud GPU only)

---

### Anthropic API

```bash
export ANTHROPIC_API_KEY="sk-ant-..."
# Add to ~/.zshrc or ~/.bashrc to persist

# Verify (requires anthropic Python package)
pip install anthropic
python -c "import anthropic; print(anthropic.__version__)"
```

- ✅  API key obtained from [console.anthropic.com](https://console.anthropic.com)
- ✅  **$30 monthly spend cap set in console** ← do this NOW
- ✅  `ANTHROPIC_API_KEY` exported in shell profile

---

### OpenRouter API (multi-provider access)

```bash
# Sign up at https://openrouter.ai/keys — free credits on signup
export OPENROUTER_API_KEY="sk-or-..."
# Add to ~/.zshrc or ~/.bashrc to persist

# Verify
curl https://openrouter.ai/api/v1/chat/completions \
  -H "Authorization: Bearer $OPENROUTER_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "model": "anthropic/claude-haiku-4-5",
    "max_tokens": 100,
    "messages": [
      {"role": "user", "content": "ping"}
    ]
  }'
```

- ✅  API key obtained from [openrouter.ai/keys](https://openrouter.ai/keys)
- ✅  `OPENROUTER_API_KEY` exported in shell profile
- ✅  curl test returns a valid response

> **Why OpenRouter:** One API key and one base URL (`https://openrouter.ai/api/v1`) gives access to Anthropic, OpenAI, Mistral, Llama, Gemini and more. Used throughout the sprint for model routing and the Day 11 multi-provider comparison.

---

### Infra toolchain (install now — needed Day 6+, painful to install mid-sprint)

```bash
brew install docker kind kubectl helm k9s

# Verify
docker --version
kind --version
kubectl version --client
helm version
k9s version
```

- 🔲 `docker` installed and daemon running
- 🔲 `kind` installed
- 🔲 `kubectl` installed
- 🔲 `helm` installed
- 🔲 `k9s` installed (optional but useful)

---

### OpenSRE (upstream reference)

```bash
# Clone as sibling to aiops-platform — do NOT clone inside the platform dir
git clone https://github.com/Tracer-Cloud/opensre \
  ~/workspace/claude-code/ai-journey/opensre-upstream

cd ~/workspace/claude-code/ai-journey/opensre-upstream

# Install OpenSRE via official installer script (SETUP.md approach did not work)
curl -fsSL https://raw.githubusercontent.com/Tracer-Cloud/opensre/main/install.sh | bash

# Onboard
opensre onboard

# Run baseline investigation
opensre investigate -i tests/e2e/kubernetes/fixtures/datadog_k8s_alert.json
```

- 🔲 Cloned to `opensre-upstream/`
- 🔲 `opensre onboard` completed
- 🔲 Baseline investigation produces a report

> **Fallback:** If setup fails after 30 min, use the Docker variant and file an issue upstream. Don't burn the day.

---

### aiops-platform skeleton

```bash
# 1. Make sure you're in the right directory
cd ~/workspace/claude-code/ai-journey/agentic-ai-projects/aiops-platform

mkdir -p agents services infra observability experiments docs demos
touch JOURNAL.md

# 2. Initialise git
git init

# 3. Now add and commit
git add .
git commit -m "chore: Day 1 skeleton — platform dirs + JOURNAL"

# 4. Create a new repo on GitHub first (go to github.com → New repository)
#    Name it: aiops-platform
#    Set it to Private
#    Do NOT initialise with README (you already have files)

# 5. Back in terminal, add the remote and push
git remote add origin https://github.com/<your-username>/aiops-platform.git
git branch -M main
git push -u origin main
git push
```

- 🔲 Skeleton dirs created
- 🔲 First commit pushed to GitHub

---

### Day 1 hello-world loop — `_scratch/day1_loop.py`

This is the first working agent you'll run. It proves your entire stack (Python env, Anthropic API, OpenRouter API, agent loop) is wired up before you write a single line of Day 2 code.

```bash
cd ~/workspace/claude-code/ai-journey/agentic-ai-projects/aiops-platform/agents/_scratch
uv venv .venv && source .venv/bin/activate
uv pip install -r requirements.txt

# Run it
python day1_loop.py
```

> **Note:** `_scratch/` is a throwaway sandbox — it has no Makefile target. All other agents use `make setup-<agent>` from the repo root. See the [Makefile quick-reference](#makefile-quick-reference) above.

**What you should see (exact format):**

```
=== via Anthropic SDK direct ===
[tool call] get_current_time()
[tool result] <current time string>
The current time is HH:MM:SS.

=== via OpenRouter ===
[tool call] get_current_time()
[tool result] <current time string>
The current time is HH:MM:SS.
```

The exact wording of the final sentence will vary — that's fine. What must be present: two `===` section headers, at least one tool call in each section, and a natural-language answer at the end of each.

**Validation checklist:**

- 🔲 Both `=== via Anthropic SDK direct ===` and `=== via OpenRouter ===` blocks appear
- 🔲 Each block shows a tool call followed by a tool result
- 🔲 Each block ends with a natural-language sentence answering the question
- 🔲 No `401 Unauthorized` — means API keys are correct
- 🔲 No `ConnectionError` — means network is up and base URLs are reachable
- 🔲 Both blocks produce the same type of answer (different wording is fine — the point is the loop ran on both paths)

> **What this validates:** Anthropic API ✓, OpenRouter API ✓, Python env ✓, venv + packages ✓, agent loop (Reason → tool call → Observe → Answer) ✓.

---

## Day 2 — Log Triage Agent

### Sample log corpus

```bash
git clone https://github.com/logpai/loghub \
  ~/workspace/claude-code/ai-journey/agentic-ai-projects/aiops-platform/services/ingestion/loghub-samples
```

- ✅ `loghub` cloned → `aiops-platform/services/ingestion/loghub-samples/`

### Agent files (already scaffolded — don't re-create)

These files are already in `aiops-platform/agents/log-intelligence/`:

| File | Backend | What it is |
|---|---|---|
| `triage.py` | all | CLI entry point. `--backend anthropic\|langchain\|openrouter` (required flag). |
| `planner_anthropic.py` | anthropic | Raw Anthropic SDK loop: manual `stop_reason` checks, budget guard. |
| `tools_anthropic.py` | anthropic | `Tools._registry` + `dispatch()` in Anthropic tool_use format. |
| `memory_anthropic.py` | anthropic | `list[dict]` message history in Anthropic message format. |
| `planner_langchain.py` | langchain | `ChatAnthropic.bind_tools()` + explicit loop. Verbose + LangSmith-traceable. |
| `planner_openrouter.py` | openrouter | `openai.OpenAI(base_url=openrouter)` loop — same model, OpenAI-compatible API. |
| `tools_openrouter.py` | openrouter | Same tool functions, OpenAI function-calling schema format. |
| `memory_openrouter.py` | openrouter | System prompt as first message in flat messages list. |
| `evaluator.py` | all | Loads `evals/cases.jsonl`, grades, CI exit codes. Backend-agnostic. |
| `evals/cases.jsonl` | all | 5 labeled test cases against `HDFS_2k.log`. |
| `requirements_anthropic.txt` | anthropic | `anthropic`, `pydantic`. |
| `requirements_langchain.txt` | langchain | `langchain`, `langchain-anthropic`, `langchain-core`, `pydantic`. |
| `requirements_openrouter.txt` | openrouter | `openai`, `pydantic`. |

### Python packages — all backends

Use `make setup-log` from the repo root — it creates the venv and installs all dependencies in one step:

```bash
cd ~/workspace/claude-code/ai-journey/agentic-ai-projects/aiops-platform
make setup-log
```

This runs `uv venv .venv` + `uv pip install -r requirements_anthropic.txt` inside `agents/log-intelligence/`. To add LangChain or OpenRouter packages manually afterward:

```bash
# LangChain backend (optional — same venv)
cd agents/log-intelligence
uv pip install -r requirements_langchain.txt --python .venv/bin/python

# OpenRouter backend (optional — same venv)
uv pip install -r requirements_openrouter.txt --python .venv/bin/python
```

- 🔲 `make setup-log` completed successfully
- 🔲 LangChain backend packages installed (optional)
- 🔲 OpenRouter backend packages installed (optional)

> **LangSmith tracing for LangChain backend:** add to `.env` to get automatic traces at [smith.langchain.com](https://smith.langchain.com):
> ```
> LANGSMITH_API_KEY=lsv2_pt_...
> LANGSMITH_TRACING=true
> LANGSMITH_PROJECT=aiops-platform
> ```

### Verify all three backends work

```bash
cd ~/workspace/claude-code/ai-journey/agentic-ai-projects/aiops-platform/agents/log-intelligence
source .venv/bin/activate

LOG=~/workspace/claude-code/ai-journey/agentic-ai-projects/aiops-platform/services/ingestion/loghub-samples/HDFS/HDFS_2k.log

python triage.py $LOG --backend anthropic    # raw Anthropic SDK
python triage.py $LOG --backend langchain    # LangChain (verbose)
python triage.py $LOG --backend openrouter   # Anthropic via OpenRouter

python triage.py --eval --backend anthropic   # Anthropic eval
python triage.py --eval --backend langchain   # LangChain eval
python triage.py --eval --backend openrouter  # OpenRouter eval
```

- 🔲 Anthropic backend produces a triage report with `## Severity` section
- 🔲 LangChain backend produces equivalent report (verbose tool traces visible)
- 🔲 OpenRouter backend produces equivalent report (usage visible in openrouter.ai dashboard)
- 🔲 `python triage.py --eval --backend anthropic` runs 5 cases and prints pass/fail counts

---

## Day 3 — Model Routing Experiment

### Prerequisites (already done in Day 1–2)

Day 3 has no new installs. All prerequisites are already in place:

| Requirement | Where set up |
|---|---|
| `OPENROUTER_API_KEY` | Day 1 — OpenRouter API section |
| `openai` Python package | Day 2 — OpenRouter backend install |
| `experiments/` directory | Already scaffolded in `aiops-platform/experiments/` |
| `run_experiment.py` | Already in `agents/log-intelligence/` |

### Verify the experiment runner is ready

```bash
cd ~/workspace/claude-code/ai-journey/agentic-ai-projects/aiops-platform/agents/log-intelligence
source .venv/bin/activate

# Smoke test — 1 case per model, confirms wiring before spending credits
python run_experiment.py --quick
```

Expected: three model blocks appear in stdout, each showing `[1/1] case-001 ... ✓` or `✗`, then a report path.

- 🔲 `run_experiment.py --quick` completes without errors on all 3 models
- 🔲 `experiments/log-triage-model-routing.md` is created after a full run

> **OpenRouter credits reminder:** The full run (3 models × 5 cases) will consume credits.
> At Haiku pricing (~$0.25/1M tokens) the entire experiment costs under $0.10.
> Sonnet is ~12× more expensive per token but still negligible at this scale.
> Top up at [openrouter.ai/settings/credits](https://openrouter.ai/settings/credits) if needed.

---

## Day 4 — PR Security Reviewer

### Semgrep + GitHub library

```bash
# Semgrep CLI
brew install semgrep
semgrep --version

# Python packages
uv pip install pygithub langchain langchain-anthropic
```

- 🔲 `semgrep` CLI installed
- 🔲 `GITHUB_TOKEN` set in environment (needs `repo` + `pull_request` scopes)
- 🔲 Python packages installed

---

## Day 5 — Slack Incident Bot + Observability

### Python packages

All bot dependencies — including `prometheus-client` — are installed with one command from the repo root:

```bash
make setup-bot
```

This creates `agents/slack-incident-bot/.venv` and installs: `slack-bolt`, `slack-sdk`, `anthropic`, `pydantic`, `python-dotenv`, `langsmith`, `prometheus-client`, `pytest`.

- 🔲 `make setup-bot` completed
- 🔲 Slack app created at [api.slack.com/apps](https://api.slack.com/apps) (socket mode enabled)
- 🔲 `SLACK_BOT_TOKEN` and `SLACK_APP_TOKEN` set in `.env`

### LangSmith (tracing)

Sign up at [smith.langchain.com](https://smith.langchain.com), then add to `agents/slack-incident-bot/.env`:

```
LANGSMITH_API_KEY=lsv2_pt_...
LANGSMITH_TRACING=true
LANGSMITH_PROJECT=slack-incident-bot
```

> **Note:** LangSmith SDK ≥ 0.2 uses `LANGSMITH_*` variable names. The old `LANGCHAIN_TRACING_V2` / `LANGCHAIN_API_KEY` names still work as a fallback but the UI shows the new names. Use `LANGSMITH_*` in all new setups.

- 🔲 LangSmith account created
- 🔲 `LANGSMITH_API_KEY`, `LANGSMITH_TRACING`, `LANGSMITH_PROJECT` set in `.env`

### Prometheus metrics

`prometheus-client` is already in `requirements.txt` and installed by `make setup-bot`. No separate install needed.

The bot exposes four metrics on `http://localhost:8000/metrics`:

| Metric | Type | Labels | What it tracks |
|---|---|---|---|
| `incident_bot_requests_total` | Counter | `status` (success/error) | Alert throughput |
| `incident_bot_duration_seconds` | Histogram | — | End-to-end `handle_alert` latency |
| `incident_bot_tokens_total` | Counter | `direction` (prompt/completion) | LLM token cost |
| `incident_bot_iterations_total` | Histogram | — | ReAct loop iterations |

Add to `agents/slack-incident-bot/.env`:

```
METRICS_ENABLED=true
METRICS_PORT=8000
```

**Validation** — after starting the bot, verify metrics are flowing:

```bash
# In one terminal: start the bot
cd agents/slack-incident-bot && python bot.py --trigger ALERT-001

# In another terminal: scrape the endpoint
curl -s http://localhost:8000/metrics | grep incident_bot
```

Expected output includes:
```
incident_bot_requests_total{status="success"} 1.0
incident_bot_duration_seconds_count 1.0
incident_bot_tokens_total{direction="prompt"} ...
incident_bot_tokens_total{direction="completion"} ...
incident_bot_iterations_total_count 1.0
```

- 🔲 `METRICS_ENABLED=true` and `METRICS_PORT=8000` set in `.env`
- 🔲 Bot starts and logs `Prometheus metrics available at http://localhost:8000/metrics`
- 🔲 `curl http://localhost:8000/metrics | grep incident_bot` returns all 4 metric families

### Run tests

```bash
make test-bot      # now runs 34 tests (23 original + 11 metrics tests)
```

- 🔲 `make test-bot` passes (34/34)

---

## Day 6 — K8s Doctor (LangGraph + kind cluster)

### Kind cluster

```bash
kind create cluster --name doctor-lab

# Deploy broken workloads for testing
# (CrashLoopBackOff + ImagePullBackOff fixtures — created during Day 6 build)
```

- 🔲 `doctor-lab` kind cluster running (`kubectl get nodes`)

### LangGraph + MCP

```bash
uv pip install langgraph langchain langchain-anthropic
uv pip install mcp   # MCP Python SDK for building the Prometheus MCP server
```

- 🔲 `langgraph` installed
- 🔲 `mcp` SDK installed

---

## Day 8 — SAST Auto-Fixer + IaC Generator

### OWASP WebGoat (SAST test target)

```bash
git clone https://github.com/WebGoat/WebGoat \
  ~/workspace/claude-code/ai-journey/agentic-ai-projects/aiops-platform/agents/sast-auto-fix/targets/WebGoat
```

- 🔲 WebGoat cloned

### IaC / RAG stack

```bash
uv pip install voyageai chromadb langchain-ollama fastapi uvicorn

# Terraform CLI
brew install terraform
terraform --version

# Checkov (IaC security scanner)
pip install checkov --break-system-packages
checkov --version
```

- 🔲 `voyageai` + `chromadb` installed
- 🔲 `langchain-ollama` installed
- 🔲 `terraform` CLI installed
- 🔲 `checkov` installed
- 🔲 `VOYAGE_API_KEY` set (sign up at [voyageai.com](https://www.voyageai.com))

---

## Day 9 — Alert Correlator + CrewAI Multi-Agent

### pgvector (vector store)

```bash
docker run -d \
  --name pgvector \
  -p 5432:5432 \
  -e POSTGRES_PASSWORD=pw \
  pgvector/pgvector:pg16

# Verify
docker ps | grep pgvector
```

- 🔲 pgvector container running

### CrewAI

```bash
uv pip install crewai crewai-tools
```

- 🔲 `crewai` installed

---

## Day 10 — Pentest Agent (Lab)

### Isolated pentest network + target

```bash
# Isolated Docker network — --internal means NO internet egress
docker network create --internal pentest-lab

# Vulnerable target (Struts2 S2-053)
docker run --rm -d \
  --network pentest-lab \
  --name target \
  vulhub/struts2-s2-053
```

- 🔲 `pentest-lab` network created
- 🔲 Target container running

### Pentest tools

```bash
brew install nmap

# Nuclei (template-based scanner)
brew install nuclei
nuclei -version

# Python packages
uv pip install python-nmap
```

- 🔲 `nmap` installed
- 🔲 `nuclei` installed

---

## Day 11 — Demos + Micro-SaaS Scaffold

### Demo recording

```bash
brew install asciinema
# agg converts asciinema recordings to GIFs
cargo install agg   # requires Rust; OR use `vhs` (below)

# Alternative: vhs (easier, no Rust needed)
brew install vhs
```

- 🔲 `asciinema` installed
- 🔲 `agg` or `vhs` installed

### Micro-SaaS scaffold

```bash
# Next.js frontend
npx create-next-app@latest \
  ~/workspace/claude-code/ai-journey/agentic-ai-projects/aiops-platform/saas/web \
  --typescript --tailwind --app

# FastAPI backend
uv pip install fastapi uvicorn sse-starlette
```

- 🔲 `saas/web` created (Next.js)
- 🔲 FastAPI backend packages installed

---

## Repos cloned — master list

All paths are absolute. `~/workspace/claude-code/ai-journey/` is the project root.

| Repo | Purpose | Local path | Day | Status |
|---|---|---|---|---|
| [Tracer-Cloud/opensre](https://github.com/Tracer-Cloud/opensre) | AIOps optional reference | `~/workspace/claude-code/ai-journey/opensre-upstream/` | 1 | 🔲 |
| [logpai/loghub](https://github.com/logpai/loghub) | Log corpus for triage agent | `~/workspace/claude-code/ai-journey/agentic-ai-projects/aiops-platform/services/ingestion/loghub-samples/` | 2 | 🔲 |
| [WebGoat/WebGoat](https://github.com/WebGoat/WebGoat) | SAST test target | `~/workspace/claude-code/ai-journey/agentic-ai-projects/aiops-platform/agents/sast-auto-fix/targets/WebGoat/` | 8 | 🔲 |

---

## Environment variables — master list

| Variable | Used by | Where to get it | Set? |
|---|---|---|---|
| `ANTHROPIC_API_KEY` | All agents | [console.anthropic.com](https://console.anthropic.com) | 🔲 |
| `GITHUB_TOKEN` | PR Reviewer (Day 4) | GitHub → Settings → Developer tokens | 🔲 |
| `SLACK_BOT_TOKEN` | Slack Bot (Day 5) | api.slack.com/apps | 🔲 |
| `SLACK_APP_TOKEN` | Slack Bot (Day 5) | api.slack.com/apps (socket mode) | 🔲 |
| `LANGSMITH_API_KEY` | LangSmith tracing (Day 2+ LangChain backend, Day 5 bot) | smith.langchain.com | 🔲 |
| `LANGSMITH_TRACING` | LangSmith tracing | Set to `true` | 🔲 |
| `LANGSMITH_PROJECT` | LangSmith tracing | Set to `aiops-platform` or per-agent name | 🔲 |
| `VOYAGE_API_KEY` | IaC Generator (Day 8) | voyageai.com | 🔲 |
| `OPENROUTER_API_KEY` | All agents (multi-provider) | [openrouter.ai/keys](https://openrouter.ai/keys) | 🔲 |

---

## Pre-Day-1 verification

Run this before starting Day 1 of `SCHEDULE.md`. **Every box must check.**

### Local tools

- 🔲 `python --version` returns 3.11.x
- 🔲 `uv --version` works
- 🔲 `docker ps` runs without errors (Docker Desktop running)
- 🔲 `ollama list` shows at least one model

### API keys (in your shell, not just `.env`)

- 🔲 `echo $ANTHROPIC_API_KEY` prints a key starting with `sk-ant-`
- 🔲 `echo $OPENROUTER_API_KEY` prints a key starting with `sk-or-`

### End-to-end hello-world

This is the gate. Full setup steps and expected output are in the **Day 1 → `_scratch/day1_loop.py`** section above. Short version:

```bash
cd ~/workspace/claude-code/ai-journey/agentic-ai-projects/aiops-platform/agents/_scratch
source .venv/bin/activate      # venv created in Day 1 section above
python day1_loop.py
```

- 🔲 `=== via Anthropic SDK direct ===` block appears, shows a tool call, ends with a time answer
- 🔲 `=== via OpenRouter ===` block appears, shows a tool call, ends with a time answer
- 🔲 No `401 Unauthorized` (keys are set) · No `ConnectionError` (network is up)

If both blocks pass, your full stack is validated. Proceed to `SCHEDULE.md` Day 1.

---

## Notes & workarounds

> Add dated notes here as you hit issues.

- `2026-04-29: OpenSRE SETUP.md instructions did not work. Used the official installer script instead: curl -fsSL https://raw.githubusercontent.com/Tracer-Cloud/opensre/main/install.sh | bash`

---

## Troubleshooting

### `day1_loop.py` returns 401 Unauthorized

- Check `.env` doesn't have quotes around the value (`KEY=sk-ant-…`, not `KEY="sk-ant-…"`)
- Check the keys are *exported* in your current shell: `echo $ANTHROPIC_API_KEY`
- Regenerate the key in the respective console if it still fails

### `ollama run` is extremely slow

- 70B model on a Mac with <32GB RAM → switch to `llama3.2:8b` or `llama3.2:3b`
- Activity Monitor showing >90% memory pressure → close other apps or use a smaller model
- First-token latency 5–15s on first call after load is normal; subsequent calls are fast

### `git check-ignore .env` says "no match"

- Make sure you're inside `aiops-platform/`, not its parent
- Verify `aiops-platform/.gitignore` exists and contains `.env`
- If missing, restore from git history or copy from the lock-in

### Docker Desktop won't start

- Open it manually from Applications first (it needs first-run permissions)
- If hung: restart Mac (works ~80% of the time)
- Last resort: `brew uninstall --cask docker && brew install --cask docker`

### `uv venv` fails with "Python not found"

- `uv` defaults to Python 3.13+; force 3.11 explicitly:
  ```bash
  uv venv --python 3.11
  ```

### Slack tokens not authenticating

- Tokens only work *after* clicking **Install App to Workspace**. Creating the app isn't enough.
- `xapp-…` is the App-Level Token (socket mode); `xoxb-…` is the Bot User OAuth Token (API calls). Don't mix them up.

---

*Last updated: 2026-05-09 · Updated through Day 5 · Proceed to [`SCHEDULE.md`](SCHEDULE.md) Day 1 once verification passes*

> 📁 This file lives in `docs/SETUP.md`. Root-level references point here.
