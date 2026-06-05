# LinkedIn Post — Day 11 Sprint Wrap

> Publish Day 12 morning after sleeping on it.
> Target: ~1,200 characters (LinkedIn sweet spot before "see more" fold).

---

**POST:**

---

I just shipped an 11-day AIOps platform sprint. Here's what's in it — and the one number that surprised me most.

**8 autonomous agents across 4 frameworks:**
• Log triage (raw Anthropic SDK) → severity + root cause in seconds
• PR security reviewer (LangChain + Semgrep) → posts GitHub comments
• Slack incident bot (LangChain + Bolt) → Block Kit cards with human approval
• K8s Doctor (LangGraph) → diagnoses CrashLoopBackOff / OOMKilled, proposes fixes
• SAST Auto-Fix (LangGraph) → finds vulns, patches them, validates in Docker
• IaC Generator (LangGraph) → Terraform from natural language
• Alert Correlator (LangGraph + MiniLM) → groups alerts by semantic similarity
• Incident Commander (CrewAI) → 4-agent crew, full triage-to-comms pipeline

**Full observability stack:** Prometheus + Loki + Promtail + Grafana. One `docker compose up`.

**Multi-provider model comparison — 5 models, 5 eval cases, real cost data:**

The number that surprised me: GPT-4o Mini passed 100% of evals at $0.0027/run but read the same 15,647 tokens on every case — it stopped after one log chunk instead of looping. Passes the rubric. Shallower than Haiku. That's a real production risk disguised as a green result.

My routing recommendation after seeing the numbers: run Haiku for all triage (100%, ~$0.02/run), auto-escalate to Sonnet on P1/P2 incidents. Blended cost ~$0.07/run with Sonnet depth where it actually matters.

Full experiment results + qualitative breakdown in the repo.

🔗 github.com/rutwickjain87/aiops-platform

What would you add to Phase 2? 👇

---

**Hashtags (paste at end):**
#AIOps #DevSecOps #LangGraph #CrewAI #Anthropic #OpenRouter #Kubernetes #MachineLearning #AIEngineering #PlatformEngineering

---

**Optional image:** Screenshot of `experiments/multi-provider-comparison.md` summary table, or one of the demo gifs (log-triage.gif is the most readable at 856K).
