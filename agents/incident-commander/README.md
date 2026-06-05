# incident-commander — Multi-Agent Incident Response Crew

> **CrewAI 4-agent system that triages, investigates, mitigates, and communicates a Kubernetes incident — end-to-end — with a mandatory human approval gate before any cluster mutation.**

<p align="center">
  <img src="../../demos/incident-commander.gif" alt="Incident Commander demo" width="900">
  <br><em>OOM cascade → 4-agent crew → human approval → kubectl patch → Slack incident card</em>
</p>

---

## Problem statement

When a Kubernetes OOM or CrashLoop cascade fires, the on-call SRE must: triage scope, dig through logs and metrics, choose and apply a fix, then communicate status — all while under pressure. Done manually this takes 15–45 minutes. A single missed step (wrong namespace, wrong deployment, no rollback plan) makes it worse.

The Incident Commander crew automates all four phases in a structured, auditable pipeline. It hands the engineer a single approval decision backed by full evidence — not a wall of kubectl output. Target: **< 5 minutes** from incident JSON to Slack card, with a human in the loop before any mutation.

---

## Architecture

```
Alert Correlator (pgvector)
        │
        ▼ incident.json
┌───────────────────────────────────────────────────────────────────┐
│  Incident Commander Crew (CrewAI)                                 │
│                                                                   │
│  Phase 1 — Parallel:                                             │
│   ┌──────────────────┐    ┌──────────────────────────────────┐   │
│   │   Triage Agent   │    │       Investigator Agent         │   │
│   │  (Claude Sonnet) │    │         (Claude Sonnet)          │   │
│   │                  │    │                                  │   │
│   │ get_pods         │    │ get_pod_logs                     │   │
│   │ get_events       │    │ query_memory_usage               │   │
│   │ get_node_status  │    │ query_cpu_usage                  │   │
│   │                  │    │ query_pod_restarts               │   │
│   │ → triage report  │    │ → root cause + confidence        │   │
│   └──────────────────┘    └──────────────────────────────────┘   │
│                 │                         │                       │
│                 └──────────┬──────────────┘                       │
│                            ▼                                      │
│  Phase 2 — Sequential:                                           │
│   ┌────────────────────────────────────────────────────────────┐  │
│   │                  Mitigator Agent (Claude Sonnet)           │  │
│   │                                                            │  │
│   │  get_deployment_status → choose tool → ⚠️ APPROVAL GATE   │  │
│   │                                                            │  │
│   │  patch_resource_limits  restart_deployment  scale_deployment│  │
│   │       (OOMKilled)          (CrashLoop)        (capacity)   │  │
│   └────────────────────────────────────────────────────────────┘  │
│                            │                                      │
│  Phase 3 — Sequential:                                           │
│   ┌────────────────────────────────────────────────────────────┐  │
│   │               Communicator Agent (Claude Haiku)            │  │
│   │                                                            │  │
│   │        post_incident_card + post_resolution_update         │  │
│   │           (Slack Block Kit — dev mode: stdout)             │  │
│   └────────────────────────────────────────────────────────────┘  │
└───────────────────────────────────────────────────────────────────┘
```

---

## Quick start

```bash
cd ~/workspace/claude-code/ai-journey/agentic-ai-projects/aiops-platform/agents/incident-commander
uv venv && source .venv/bin/activate
uv pip install -r requirements.txt

# Copy and fill in env vars
cp .env.example .env   # set ANTHROPIC_API_KEY and LANGSMITH_API_KEY

# Demo mode — runs against a synthetic OOM incident on your kind cluster
python respond.py --demo oom

# Skip approval gate for CI/testing
REQUIRE_HUMAN_APPROVAL=false python respond.py --demo oom

# Full pipeline — takes incident JSON from the Alert Correlator
python respond.py --incident incidents.json
```

---

## Agents

| Agent | Model | Tools | Output |
|---|---|---|---|
| **Triage** | `claude-sonnet-4-6` | `get_pods_in_namespace`, `get_events`, `get_node_status` | Severity classification, blast radius, urgency |
| **Investigator** | `claude-sonnet-4-6` | `get_pod_logs`, `describe_pod`, `query_memory_usage`, `query_cpu_usage`, `query_pod_restarts` | Root cause hypothesis + evidence + confidence |
| **Mitigator** | `claude-sonnet-4-6` | `get_deployment_status`, `patch_resource_limits`, `restart_deployment`, `scale_deployment` | Remediation action + verification |
| **Communicator** | `claude-haiku-4-5` | `post_incident_card`, `post_resolution_update` | Slack Block Kit incident + resolution cards |

The Communicator uses Haiku (cheaper, deterministic formatting) while the three reasoning agents use Sonnet. This alone saves ~60% on the communication step — the most token-heavy output, but not the hardest reasoning task.

---

## SRE metrics

| Metric | Value |
|---|---|
| End-to-end latency (OOM demo) | ~3–5 min (Sonnet × 3 phases) |
| Latency — Phase 1 parallel | ~45–60s (Triage + Investigator concurrent) |
| Latency — Phase 2 Mitigator | ~30–45s |
| Latency — Phase 3 Communicator | ~15s |
| LLM cost per incident (Sonnet × 3 + Haiku × 1) | ~$0.08–$0.15 |
| Human decisions required | 1 (Mitigator approval gate) |
| Scenarios tested | OOM cascade, node pressure |

---

## Failure modes

| Failure | Symptom | Mitigation |
|---|---|---|
| Mitigator describes fix in text, doesn't call tool | Approval gate never fires; "resolved" in text only | `🔧 MUTATING TOOL CALLED` sentinel at tool boundary; tighten task description to require tool invocation |
| Agent writes "I would patch limits" without calling `patch_resource_limits` | No sentinel print, no approval prompt | Structural fix: add `output_pydantic=MitigationResult` to Task to reject text-only answers |
| `KUBECONFIG=~/.kube/config` in `.env` not expanded | `localhost:8080` connection refused | Use absolute path or `os.path.expanduser()` at load time |
| CrewAI ≥ 0.80 ValidationError | `Agent(llm=ChatAnthropic(...))` raises Pydantic error | Use `crewai.LLM(model="anthropic/claude-sonnet-4-6")` |
| Approval gate blocks on EOF (CI/piped input) | `EOFError` crashes the process | `try/except EOFError` in `_approval_gate()` → rejects action for safety |
| Slack token not set | Card posted to stdout (dev mode) | Expected — set `SLACK_BOT_TOKEN=xoxb-...` for real posting |
| `max_iter` guillotine fires | Mitigator forced answer at `max_iter=6` without tool call | Raise `max_iter` or add `output_pydantic` validation; prompt more explicit about tool requirement |
| No rollback on failed patch | Memory limit set too high causes OOM on all nodes | Add `--dry-run=server` pre-flight + rollback to previous resource limits |

---

## Production gaps

| Capability | Current (Dev) | Production |
|---|---|---|
| HITL | `input()` blocks stdin | Async Slack webhook with timeout |
| Rollback | None | Snapshot + automated rollback on failure |
| RBAC | Personal kubeconfig (likely cluster-admin) | Service account with minimal permissions |
| Dry-run | None | `kubectl --dry-run=server` before apply |
| Approval timeout | None | Auto-reject after 5 min |
| Multi-incident | Sequential | Priority queue with concurrent crews |
| Cost guard | None | Halt if spend > $1.00/incident |
| Embedding validation | Agent text = evidence | `output_pydantic=MitigationResult` on Task |

---

## Environment variables

| Variable | Default | Notes |
|---|---|---|
| `ANTHROPIC_API_KEY` | required | Powers all 4 agents |
| `LANGSMITH_API_KEY` | optional | LangSmith traces |
| `LANGSMITH_PROJECT` | `aiops-incident-commander` | LangSmith project name |
| `KUBECONFIG` | `/Users/<you>/.kube/config` | Use absolute path — `~` not shell-expanded in `.env` |
| `KUBE_CONTEXT` | `kind-doctor-lab` | kubectl context |
| `PROMETHEUS_URL` | `http://localhost:9090` | For the Investigator's metric queries |
| `SLACK_BOT_TOKEN` | empty | Leave unset for dev mode (stdout); set `xoxb-...` for real Slack |
| `SLACK_INCIDENT_CHANNEL` | `#incidents` | Channel for incident cards |
| `REQUIRE_HUMAN_APPROVAL` | `true` | Set `false` to skip approval gate (CI/demo) |
