# AIOps Platform — Daily Operations Schedule

Operational runbook for working with the Slack Incident Bot and its LangSmith observability layer. Covers the daily rhythm of a developer actively building or maintaining the Day 5 agent.

---

## Morning Start (~09:00)

### 1. Verify the bot is healthy

```bash
cd ~/workspace/claude-code/ai-journey/agentic-ai-projects/aiops-platform

# If this is a fresh clone or venv is missing, set it up first:
# make setup-bot

# Quick sanity check — dry-run, no Slack connection needed
agents/slack-incident-bot/.venv/bin/python -c "
import sys, os
sys.path.insert(0, 'agents/slack-incident-bot')
from planner import IncidentPlanner
p = IncidentPlanner()          # no slack_client = dry-run mode
r = p.handle_alert('ALERT-001')
print(r)
"
```

Expected output includes `"status": "done"` and a dry-run `ts`.

### 2. Check LangSmith for overnight traces

1. Open [smith.langchain.com](https://smith.langchain.com) → project `slack-incident-bot`
2. Filter by **Last 24 hours**
3. Review any runs that errored (red dot) — note the `alert_id` from inputs
4. Check average latency and token counts — flag if p99 > 5 s or cost > $0.01/alert

### 3. Confirm the Slack bot is running (if deployed)

```bash
# If running as a background process
pgrep -fa "python bot.py" || echo "Bot not running — start with: python bot.py"

# Or check socket mode connection log
tail -f /var/log/aiops/incident-bot.log | grep -E "(Connected|error|WARNING)"
```

---

## During the Day — Incident Response Workflow

When a real (or simulated) alert fires, the bot follows this flow. Use this checklist to verify each step works end-to-end:

### Step 1 — Alert fires

```bash
# Simulate any of the three synthetic alerts
python bot.py --trigger ALERT-001   # P1: HDFS replication
python bot.py --trigger ALERT-002   # P2: API gateway latency
python bot.py --trigger ALERT-003   # P3: K8s pod restart
```

### Step 2 — Verify the Slack card appeared

Check `#incidents` channel for a card with:
- Correct severity emoji (🔴 P1, 🟠 P2, 🟡 P3)
- Service name and trigger time
- Root cause hypothesis citing metric values
- Up to 5 ordered remediation steps
- Three buttons: ✅ Acknowledge  🚨 Escalate  ❌ Dismiss

### Step 3 — Verify LangSmith trace captured the run

1. LangSmith → project → click the new `incident_planner.handle_alert` run
2. Confirm two child LLM runs: one for `get_alert_context`, one for `post_incident_card`
3. Inspect the `post_incident_card` tool input — verify `root_cause` and `suggested_actions` are populated

### Step 4 — Human action (button click)

Click one of the three buttons in Slack.  The card should update in-place:
- Buttons disappear
- Footer shows `Updated by @you · HH:MM UTC DD Mon YYYY`
- Status emoji changes (👀 acknowledged / 🚨 escalated / ❌ dismissed)

---

## Development Cycle — Adding or Changing Tools

When modifying tools, follow this order to avoid breaking the agent:

1. Edit `tools.py` — update schema and/or function
2. Run unit tests:
   ```bash
   make test-bot
   # Or to run a subset: agents/slack-incident-bot/.venv/bin/pytest tests/test_slack_bot.py -v -k "AlertContext or IncidentCard"
   ```
3. Dry-run the planner to verify the agent still uses the tool correctly:
   ```bash
   python -c "from planner import IncidentPlanner; print(IncidentPlanner().handle_alert('ALERT-002'))"
   ```
4. Check LangSmith — the new tool call should appear as a sibling LLM run
5. Lint:
   ```bash
   ruff check agents/slack-incident-bot/ tests/test_slack_bot.py
   ruff format agents/slack-incident-bot/ tests/test_slack_bot.py
   ```

---

## Weekly — LangSmith Observability Review

Perform once per week (or after any significant volume of alerts):

### Token usage audit

In LangSmith → project → **Monitor** tab:

| Metric | Target | Action if exceeded |
|--------|--------|--------------------|
| Avg tokens / alert | < 800 | Shorten system prompt |
| p99 latency | < 4 s | Check Haiku API status |
| Error rate | < 2% | Review error traces |
| Cost / 100 alerts | < $0.05 | Acceptable for Haiku |

### Prompt quality review

1. Filter runs where `iterations > 2` — these indicate the agent looped unexpectedly
2. Open one and inspect: did the model call a wrong tool? Hallucinate a tool name?
3. If `post_incident_card` inputs are thin (short `root_cause`), tighten the system prompt in `memory.py`

### Trace tagging

LangSmith runs are tagged `slack-incident-bot`. You can filter by tag to isolate
incident-bot traces from other project agents (e.g., `pr-reviewer`).

---

## End of Day

### Commit any changes

```bash
cd ~/workspace/claude-code/ai-journey/agentic-ai-projects/aiops-platform

# Stage only agent and docs changes
git add agents/slack-incident-bot/ tests/test_slack_bot.py docs/
git status   # review before committing

git commit -m "feat(day5): <short description>"
git push
```

### Update JOURNAL.md

Add the day's entry under the relevant day section:
- What you built
- Key concepts learned
- Errors encountered and how they were resolved
- LangSmith observations (token counts, latency, any prompt tweaks)

---

## Troubleshooting Quick Reference

| Symptom | Likely cause | Fix |
|---------|-------------|-----|
| `SLACK_CHANNEL_ID not set` | Missing env var | Copy `.env.example` → `.env`, fill values |
| Bot posts card but buttons don't work | Interactivity not enabled | api.slack.com → Features → Interactivity & Shortcuts → toggle ON |
| `No module named 'langsmith'` | langsmith not installed | `make setup-bot` (reinstalls all deps) |
| LangSmith traces not appearing | `LANGSMITH_TRACING` not `true`, or wrong key name | Check `.env` uses `LANGSMITH_TRACING=true` (not `LANGCHAIN_TRACING_V2`) |
| `index.lock` git error | Stale lock file | `rm .git/index.lock` |
| Agent exceeds MAX_ITERATIONS | LLM not calling tools | Check system prompt in `memory.py`; verify tool schemas |
| Slack 401 on `chat_postMessage` | Wrong token or expired | Re-install app from api.slack.com → OAuth & Permissions |
