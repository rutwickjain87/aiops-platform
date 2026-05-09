# AIOps Platform — Setup Guide

End-to-end setup for the **Slack Incident Bot** (Day 5 agent), including the LangSmith observability layer.

---

## Prerequisites

| Tool | Version | Install |
|------|---------|---------|
| Python | ≥ 3.11 | [python.org](https://python.org) |
| uv | latest | `curl -LsSf https://astral.sh/uv/install.sh \| sh` |
| git | any | system package manager |

---

## 1. Clone and configure the workspace

```bash
git clone https://github.com/rutwickjain87/ai-journey.git
cd ai-journey/agentic-ai-projects/aiops-platform
```

Copy the root-level environment template and fill in your keys:

```bash
cp .env.example .env
```

The bot also has its own `.env.example` with more detailed comments:

```bash
cp agents/slack-incident-bot/.env.example agents/slack-incident-bot/.env
```

---

## 2. Create and activate the virtual environment

Use `make setup-bot` from the repo root — it creates the venv and installs all dependencies in one step:

```bash
make setup-bot
```

This runs `uv venv .venv` + `uv pip install -r requirements.txt` inside `agents/slack-incident-bot/` and targets the correct Python interpreter automatically.

> **Manual alternative** (only if you can't use Make):
> ```bash
> cd agents/slack-incident-bot
> uv venv .venv
> uv pip install -r requirements.txt --python .venv/bin/python
> ```

> **Important:** Never activate the venv and run `uv pip install` without `--python` — it may install into the wrong interpreter when multiple venvs exist in the repo.

---

## 3. Anthropic API key

1. Go to [console.anthropic.com](https://console.anthropic.com) → API keys → **Create key**
2. Add to `.env`:
   ```
   ANTHROPIC_API_KEY=sk-ant-...
   ```

The planner uses `claude-haiku-4-5-20251001` — fast and inexpensive for 2-step incident triage.

---

## 4. Slack app creation

### 4a. Create the app

1. Visit [api.slack.com/apps](https://api.slack.com/apps) → **Create New App → From scratch**
2. Name it `AIOps Incident Bot`, select your workspace, click **Create App**

### 4b. Enable Socket Mode

1. Sidebar → **Settings → Socket Mode** → toggle **Enable Socket Mode** ON
2. Name the token `incident-bot-socket` → **Generate**
3. Copy the `xapp-1-...` token → `.env` as `SLACK_APP_TOKEN`

### 4c. Bot token scopes

1. Sidebar → **Features → OAuth & Permissions → Scopes → Bot Token Scopes**
2. Add these scopes:

   | Scope | Purpose |
   |-------|---------|
   | `chat:write` | Post and update incident cards |
   | `chat:write.public` | Post to channels without joining |
   | `channels:read` | Resolve channel names |
   | `reactions:write` | Optional: add emoji reactions |

3. Scroll up → **Install to Workspace** → **Allow**
4. Copy the `xoxb-...` **Bot User OAuth Token** → `.env` as `SLACK_BOT_TOKEN`

### 4d. Enable Events API + Interactivity

**Events API** (required for `app_mention` if needed later):

1. Sidebar → **Features → Event Subscriptions** → toggle ON
2. Subscribe to bot events: `app_mention`, `message.channels`

**Interactivity** (required for button clicks — Acknowledge / Escalate / Dismiss):

1. Sidebar → **Features → Interactivity & Shortcuts** → toggle ON
2. With Socket Mode enabled the Request URL field is ignored — just save

### 4e. Find your channel ID

1. Right-click the `#incidents` channel in Slack → **Copy link**
2. The URL contains the channel ID: `C0XXXXXXXXX`
3. Add to `.env` as `SLACK_CHANNEL_ID`
4. Invite the bot to the channel: `/invite @AIOps Incident Bot`

---

## 5. LangSmith observability

LangSmith traces every LLM call and the full incident pipeline. It's optional but highly recommended — it lets you see exactly what prompts the model received, how many tokens were used, and where latency comes from.

### 5a. Create a LangSmith account

1. Visit [smith.langchain.com](https://smith.langchain.com) → sign up (free tier available)
2. Go to **Settings → API Keys → Create API Key**
3. Copy the `ls__...` key

### 5b. Create a project

1. In LangSmith sidebar → **Projects → New Project**
2. Name it `slack-incident-bot` (or match your `LANGSMITH_PROJECT` env var)

### 5c. Add to `.env`

```bash
LANGSMITH_API_KEY=lsv2_pt_...
LANGSMITH_TRACING=true
LANGSMITH_PROJECT=slack-incident-bot
```

> **Variable naming:** LangSmith SDK ≥ 0.2 uses `LANGSMITH_*` names. The old `LANGCHAIN_TRACING_V2` / `LANGCHAIN_API_KEY` names still work as a fallback, but the LangSmith UI and new projects expect `LANGSMITH_*`. Always use the new names.

### 5d. What you'll see

Each call to `handle_alert()` creates one trace tree:

```
┌─ incident_planner.handle_alert  [chain]
│    input:  { alert_id: "ALERT-001" }
│    output: { incident_id: "INC-...", ts: "...", status: "done", iterations: 2 }
│
├─ ChatAnthropic  [llm]   ← turn 1: reads alert context
│    model:  claude-haiku-4-5-20251001
│    tokens: prompt / completion / total
│
└─ ChatAnthropic  [llm]   ← turn 2: posts incident card
     model:  claude-haiku-4-5-20251001
     tokens: prompt / completion / total
```

To disable tracing without removing the keys: set `LANGSMITH_TRACING=false`.

---

## 6. Run the bot

```bash
# Start the Socket Mode listener (no alerts yet)
python bot.py

# Fire a test alert immediately on startup, then keep listening
python bot.py --trigger ALERT-001
python bot.py --trigger ALERT-002
python bot.py --trigger ALERT-003
```

You should see an incident card appear in `#incidents` with three buttons: ✅ Acknowledge, 🚨 Escalate, ❌ Dismiss.

---

## 7. Run the tests

The full test suite runs without any Slack or Anthropic credentials. From the repo root:

```bash
make test-bot
```

Expected output: **24 passed**.

> **Manual alternative:** `agents/slack-incident-bot/.venv/bin/pytest tests/test_slack_bot.py -v` from the repo root. Run `make setup-bot` first if the venv doesn't exist yet.

---

## 8. Verify LangSmith traces

After running `python bot.py --trigger ALERT-001`:

1. Open [smith.langchain.com](https://smith.langchain.com)
2. Navigate to your `slack-incident-bot` project
3. You should see one run named `incident_planner.handle_alert`
4. Expand it to see the two `ChatAnthropic` child runs with full prompt/response payloads

---

## Environment variable reference

| Variable | Required | Description |
|----------|----------|-------------|
| `ANTHROPIC_API_KEY` | ✅ | Anthropic API key |
| `SLACK_BOT_TOKEN` | ✅ (live) | Bot User OAuth token (`xoxb-...`) |
| `SLACK_APP_TOKEN` | ✅ (live) | Socket Mode app token (`xapp-1-...`) |
| `SLACK_CHANNEL_ID` | ✅ (live) | Target channel for incident cards |
| `LANGSMITH_API_KEY` | optional | LangSmith API key (from smith.langchain.com) |
| `LANGSMITH_TRACING` | optional | Set to `true` to enable tracing |
| `LANGSMITH_PROJECT` | optional | LangSmith project name (default: `slack-incident-bot`) |
