# demos/

Demo recordings for the three flagship agents. Each `.tape` file is a [VHS](https://github.com/charmbracelet/vhs) script that records a terminal session to an animated gif.

## Prerequisites

```bash
brew install vhs
# vhs requires ffmpeg for gif encoding
brew install ffmpeg
```

## Recording

```bash
# From the repo root — record all three demos
cd ~/workspace/claude-code/ai-journey/agentic-ai-projects/aiops-platform

vhs demos/log-triage.tape           # → demos/log-triage.gif
vhs demos/k8s-doctor.tape           # → demos/k8s-doctor.gif
vhs demos/incident-commander.tape   # → demos/incident-commander.gif
```

Each tape file has a **Prerequisites** comment at the top — read it before running. The main requirements are:
- Active venv with agent dependencies installed
- `ANTHROPIC_API_KEY` exported
- `kind-doctor-lab` cluster running (for K8s Doctor and Incident Commander)

## What each demo shows

| Tape | Duration | What you see |
|---|---|---|
| `log-triage.tape` | ~2 min | Agent triages a 2 000-line HDFS log: tool calls (grep, read_log_chunk, cluster_errors), structured Markdown report (Severity, Root Cause, Actions), then eval suite (5/5 pass) |
| `k8s-doctor.tape` | ~2.5 min | LangGraph observe→hypothesize→propose pipeline diagnosing CrashLoopBackOff and OOMKilled; model routing shown (Haiku for observe, Sonnet for reason) |
| `incident-commander.tape` | ~3 min | 4-agent CrewAI crew handling an OOM cascade: parallel Triage+Investigator, approval gate fires, Mitigator patches resource limits, Communicator posts Slack Block Kit card |

## Embedding in READMEs

After recording, gifs are referenced from each agent's README:

```markdown
<p align="center">
  <img src="../../demos/log-triage.gif" alt="Log Triage Agent demo" width="900">
</p>
```

Use a relative path from the agent directory to `demos/`.
