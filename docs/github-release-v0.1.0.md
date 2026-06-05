# GitHub Release — v0.1.0

> Copy-paste this into the GitHub Release editor at:
> https://github.com/rutwickjain87/aiops-platform/releases/new?tag=v0.1.0

---

**Release title:** `v0.1.0 — 11-Day AIOps Platform Sprint`

---

**Release body:**

---

## What's in this release

An end-to-end AIOps platform built in 11 days — 8 autonomous agents across 4 frameworks, full observability, a micro-SaaS skeleton, and a multi-provider model comparison with real numbers.

### Agents

| Agent | Framework | What it does |
|---|---|---|
| [Log Intelligence](agents/log-intelligence/) | Raw Anthropic SDK + OpenRouter | Triages HDFS logs — severity, root cause hypothesis, suggested actions |
| [PR Reviewer](agents/pr-reviewer/) | LangChain | Security-focused code review via Semgrep + LLM, posts GitHub comments |
| [Slack Incident Bot](agents/slack-incident-bot/) | LangChain + Slack Bolt | Summarises alerts into Block Kit cards, supports human approval buttons |
| [K8s Doctor](agents/k8s-doctor/) | LangGraph | Diagnoses CrashLoopBackOff / OOMKilled / ImagePullBackOff and proposes fixes with a human-in-the-loop `--apply` gate |
| [SAST Auto-Fix](agents/sast-auto-fix/) | LangGraph | Finds vulnerabilities with Semgrep, patches them with an LLM, validates fix in Docker |
| [IaC Generator](agents/iac-generator/) | LangGraph | Generates and validates Terraform from natural language prompts |
| [Alert Correlator](agents/alert-correlator/) | LangGraph + sentence-transformers | Groups firing alerts by semantic similarity using local MiniLM embeddings |
| [Incident Commander](agents/incident-commander/) | CrewAI | Four-agent crew (Triage → RCA → Remediation → Communication) with Slack Block Kit output |

### Observability stack

Full Prometheus + Loki + Promtail + Grafana setup in `observability/` — one `docker compose up` gets you metrics, logs, and dashboards for every agent.

### Micro-SaaS scaffold

`saas/api/` — FastAPI service wrapping the IaC Generator as a streaming SSE endpoint (`POST /runs`, `GET /runs/{id}`, `GET /healthz`). Stub Supabase auth and Stripe billing hooks ready for Phase 2.

`saas/web/` — Next.js 14 + Tailwind frontend wired to the streaming API.

### Multi-provider model comparison

5 models × 5 eval cases via OpenRouter. Full results in [`experiments/multi-provider-comparison.md`](experiments/multi-provider-comparison.md).

| Model | Pass rate | p50 latency | Avg $/run |
|---|---|---|---|
| Claude Sonnet 4.6 | 5/5 (100%) | 40.9s | $0.2224 |
| Claude Haiku 4.5 | 5/5 (100%) | 21.0s | $0.0227 |
| GPT-4o Mini | 5/5 (100%) | 14.1s | $0.0027 |
| Llama 3.1 70B | 4/5 (80%) | 13.9s | $0.0087 |
| Mistral Nemo 12B | 4/5 (80%) | 6.4s | $0.0006 |

**Recommendation:** Haiku for production triage (100%, $0.023/run), escalate to Sonnet for P1/P2, GPT-4o Mini for prompt iteration.

### Demo recordings

Three terminal gifs in `demos/` — one per flagship agent.

---

### What's next (Phase 2)

- Deployed infra (EKS + Helm charts)
- Real auth (Supabase JWT) and billing (Stripe metered usage)
- CI evals on every PR for all agents
- Production-grade HITL approval flow

---

**Assets to attach:** none (gifs are committed to the repo under `demos/`)
