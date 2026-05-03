# Postmortem — INC-2026-04-15-001 — Mitigator picked wrong root cause during checkout latency drill

**Severity:** SEV-2 · **Duration:** 23 min · **Author:** Rutwick (on-call)
**Status:** Final · **Drill / Real:** Synthetic drill (staging cluster)
**Blameless:** Yes — focus on systems and agent design, not individuals.

---

## Summary

During a scheduled SEV-2 drill on 2026-04-15, the `checkout` service in staging began returning 5xx errors at ~14% rate. The Incident Commander correctly opened an incident and dispatched its specialist sub-agents within 22 seconds. The **Investigator** agent and the **K8s Doctor** (invoked as a tool by the Investigator) returned *competing* root-cause hypotheses. The orchestrator silently selected the higher-confidence Investigator hypothesis — *connection pool exhaustion* — and the Mitigator proposed bumping the pool size. The on-call engineer (me) overrode the proposal during the approval gate, recognizing from memory that the symptom matched a known OOM signature, and bumped the pod memory limit instead. The drill recovered within 23 minutes — 6 minutes over the 17-minute target.

**The agent system reached the wrong remediation.** Without human override, the proposed action would have been applied and would not have fixed the issue.

## Impact

- Drill MTTR: **23 min** (target: 17 min, single-agent baseline: 41 min)
- No customer impact (staging only)
- Wasted human attention: ~5 minutes spent challenging the agent's confident-but-wrong proposal
- Trust hit: this is the third drill where multi-agent disagreement was masked from the operator

## Timeline (UTC)

| Time | Event | Source |
|---|---|---|
| 14:02:11 | Synthetic fault injected: memory pressure on `checkout` pods (limit dropped to 256Mi) | drill harness |
| 14:02:34 | Prometheus alert `checkout_5xx_rate_high` fires | observability/prometheus/checkout.yaml |
| 14:02:36 | Incident Commander opens incident `INC-2026-04-15-001`; Slack channel `#inc-2026-04-15-001` auto-created | LangSmith trace [a1f2…] |
| 14:02:58 | Triage Agent classifies SEV-2; routes to Investigator + Communicator in parallel | trace [b3c1…] |
| 14:03:42 | Investigator queries DB metrics: pool wait time p99 = 2.1s (high). Hypothesis: **connection pool exhaustion**. Confidence 0.78. | trace [c4d2…] |
| 14:04:11 | Investigator invokes K8s Doctor as a tool. K8s Doctor returns: 4 OOMKilled events in last 90s on `checkout` pods. Hypothesis: **OOM**. Confidence 0.71. | trace [d5e3…] |
| 14:04:12 | Investigator's final report cites pool exhaustion. K8s Doctor's hypothesis appended as a footnote. | trace [d5e3…] |
| 14:04:30 | Mitigator picks Investigator's hypothesis (higher confidence). Proposes: `kubectl set resources deployment/checkout --requests=connections=200`. Approval requested in Slack. | trace [e6f4…] |
| 14:06:03 | I (on-call) reviewed the proposal. Recognized OOM pattern from drill INC-2026-03-22 (similar cause). Rejected. | Slack |
| 14:08:17 | I posted manual remediation: `kubectl set resources deployment/checkout --limits=memory=512Mi`. Mitigator did not propose this. | Slack |
| 14:08:42 | New deployment rolled out | kubectl rollout status |
| 14:24:51 | Error rate drops below 1%. Incident closed. | Prometheus |

## Root cause

**Two layers, one shared root cause.**

The injected fault (memory pressure → OOMKills) caused checkout pods to be restarted. During restarts, in-flight DB connections were not gracefully closed, leaking from the pool. The Investigator saw the *symptom* of the leak (pool wait time) and the K8s Doctor saw the *cause* (OOMKills). Both were technically correct in isolation. The actual root cause is OOM; the pool exhaustion is downstream.

**Why the agent system got it wrong:**

The Incident Commander has no mechanism to *resolve* competing hypotheses between sub-agents. It defaults to the highest-confidence single hypothesis. Confidence scores are produced independently by each sub-agent and are not directly comparable — the Investigator's 0.78 and the K8s Doctor's 0.71 don't sit on the same scale.

## What went well

- Detection in **23 seconds** from fault injection to alert — well within target
- Auto-opening of the incident channel + auto-paging worked first try
- LangSmith traces let me reconstruct every agent decision in under 2 minutes during the postmortem
- The approval gate functioned as designed — the wrong action was *proposed*, not *applied*
- Slack interactive UX for the approval gate was clear; rejection took two clicks

## What went wrong

- **The orchestrator silently merged competing hypotheses.** The K8s Doctor's OOM hypothesis was demoted to a footnote rather than presented as a peer.
- **Confidence scores from different sub-agents are not comparable.** Treating them as if they were is a design flaw.
- **No prior-incident memory.** The cluster had a near-identical OOM drill 24 days prior. The agent system did not retrieve it. I did, from human memory.
- **The Mitigator's proposal lacked counterfactuals.** It said "this will fix it" rather than "this is the most likely fix; here are the others I considered."

## Root cause analysis (5 whys)

1. **Why was the wrong remediation proposed?** Mitigator received only one hypothesis from the orchestrator.
2. **Why only one?** Orchestrator picks the highest-confidence single hypothesis when sub-agents disagree.
3. **Why does it pick instead of presenting both?** Initial design optimized for "one decision, one action" simplicity.
4. **Why was that the design choice?** I was anchored on the single-agent baseline pattern; multi-agent disagreement was treated as an edge case rather than a first-class state.
5. **Why didn't the eval set catch this?** The synthetic incident corpus has 10 cases, none of which exercise sub-agent disagreement.

## Action items

| # | Action | Owner | Priority | Due | Status |
|---|---|---|---|---|---|
| 1 | When sub-agents return competing hypotheses, surface BOTH to human via approval gate (do not silently pick) | Rutwick | P0 | 2026-04-22 | open |
| 2 | Add 10 cases to `evals/incidents.jsonl` covering sub-agent disagreement scenarios (OOM-vs-pool, GC-vs-CPU, network-vs-DNS, etc.) | Rutwick | P0 | 2026-04-29 | open |
| 3 | Calibrate confidence scoring: train sub-agents on a held-out set so confidence numbers are comparable across agents | Rutwick | P1 | 2026-05-13 | open |
| 4 | Add prior-incident retrieval to Mitigator: query `docs/postmortems/` + long-term memory for similar past incidents before proposing | Rutwick | P1 | 2026-05-06 | open |
| 5 | Mitigator's proposal must include "alternatives considered" in approval message | Rutwick | P1 | 2026-05-06 | open |
| 6 | Add Prometheus rule: alert if a SEV-1/2 incident has competing hypotheses (use this as a signal we need rule #1's fix) | Rutwick | P2 | 2026-05-13 | open |

## Lessons learned

- **Multi-agent systems amplify wrong reasoning when the orchestrator collapses disagreement.** Disagreement is information; surface it, don't hide it.
- **Confidence scores across heterogeneous agents are not comparable.** Treat them as a signal of *certainty within the agent's frame*, not an absolute ranking.
- **The eval set is a living artifact.** This incident was a missing eval case. Every postmortem should produce at least one new eval entry. (See action item #2.)
- **Approval gates are the primary safety mechanism.** The system worked because the gate exists. Future agent designs should assume the gate will sometimes catch the agent — and use that as a teaching signal, not just a safety valve.
- **Prior-incident retrieval is non-negotiable for SRE agents.** Humans use memory; agents must too.

## Trace artifacts

- LangSmith parent trace: `a1f2-…-9b21` ([link](#))
- Sub-agent traces: Investigator [c4d2-…], K8s Doctor [d5e3-…], Mitigator [e6f4-…]
- Slack channel archive: `#inc-2026-04-15-001`
- Prometheus snapshot: `observability/snapshots/2026-04-15-checkout.json`

## Sign-off

- Author: Rutwick — 2026-04-15
- Reviewer: <peer reviewer> — pending
- Distribution: `#aiops-agents`, platform team
