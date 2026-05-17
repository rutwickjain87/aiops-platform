# K8s Doctor — Model Routing Experiment

> Generated: 2026-05-15  
> Cases: 5 | Eval set: `evals/cases.jsonl`  
> Cost estimates based on token averages — cross-check with LangSmith for actuals.

## Routing strategies compared

| Strategy | observe node | hypothesize node | propose node |
|---|---|---|---|
| **Routing ON** | `claude-haiku-4-5` | `claude-sonnet-4-6` | `claude-sonnet-4-6` |
| **Routing OFF** | `claude-sonnet-4-6` | `claude-sonnet-4-6` | `claude-sonnet-4-6` |

**Rationale:** `observe` runs read-only kubectl commands and extracts signals —
a cheap, deterministic task. `hypothesize` and `propose` require complex reasoning
over ambiguous data — the task where Sonnet's quality advantage shows.

## Results summary

| Metric | Routing ON | Routing OFF | Delta |
|---|---|---|---|
| Pass rate | 100% (5/5) | 100% (5/5) | +0pp |
| Avg latency | 39.3s | 50.5s | -11.2s |
| p50 latency | 40.0s | 51.6s | — |
| Est. $/run | $0.0201 | $0.0264 | 24% cheaper |
| Est. $/5 cases | $0.100 | $0.132 | — |

## Per-case breakdown

### Routing ON

| Case | Pass | Latency | Notes |
|---|---|---|---|
| case-001 | ✅ | 45.9s | — |
| case-002 | ✅ | 35.3s | — |
| case-003 | ✅ | 43.4s | — |
| case-004 | ✅ | 40.0s | — |
| case-005 | ✅ | 32.0s | — |

### Routing OFF (all Sonnet)

| Case | Pass | Latency | Notes |
|---|---|---|---|
| case-001 | ✅ | 52.2s | — |
| case-002 | ✅ | 44.3s | — |
| case-003 | ✅ | 57.2s | — |
| case-004 | ✅ | 51.6s | — |
| case-005 | ✅ | 47.2s | — |

## Qualitative observations

### Routing ON (haiku observe + sonnet reason)

<!-- Fill in after reviewing diagnosis outputs -->
- Output quality: (Excellent / Good / Acceptable / Poor)
- Root cause accuracy: (correct / partial / wrong) — note which cases
- Remediation specificity: (specific kubectl commands / generic / missing)
- Notable failure modes: (list, or 'None observed')

### Routing OFF (all Sonnet)

<!-- Fill in after reviewing diagnosis outputs -->
- Output quality: (Excellent / Good / Acceptable / Poor)
- Root cause accuracy: (correct / partial / wrong)
- Remediation specificity:
- Notable failure modes:

## Recommendation

<!-- Fill in based on your observations -->

**Production (on-call SRE relies on this):** [Routing ON / OFF] — [reason]

**Development / prompt tuning:** [Routing ON — cost-optimized] — reason: observe
node uses haiku for raw signal extraction which doesn't require high reasoning
quality; only the hypothesis and remediation nodes benefit from Sonnet.

**Estimated savings at scale:** If the agent runs 100×/day:
  - Routing ON:  $2.01/day
  - Routing OFF: $2.64/day
  - Saving: $0.63/day  ($231/year)

## How to reproduce

```bash
cd agents/k8s-doctor

# Full experiment (both strategies × 5 cases)
python evals/run_routing_experiment.py

# Quick smoke test (1 case each)
python evals/run_routing_experiment.py --quick

# Run eval with routing ON manually
OBSERVE_MODEL=claude-haiku-4-5-20251001 REASON_MODEL=claude-sonnet-4-6 \
  python evals/run_eval.py

# Run eval with routing OFF (all Sonnet)
OBSERVE_MODEL=claude-sonnet-4-6 REASON_MODEL=claude-sonnet-4-6 \
  python evals/run_eval.py
```
