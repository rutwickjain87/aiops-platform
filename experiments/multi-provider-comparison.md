# Multi-Provider Comparison — Log Triage Agent

> Generated: 2026-05-20 13:07 UTC  |  Eval: 5 eval cases  |  Agent: Day-2 log triage  |  Log: HDFS_2k.log
>
> **Why this matters:** Provider choice is an engineering decision with measurable cost, quality, and latency trade-offs.
> This experiment gives you real numbers — not opinions — for a structured log triage task.

---

## Summary table

| Model | Provider | Pass rate | p50 latency | p95 latency | Avg $/run | Sections present | P-level format | Log citations |
|---|---|---|---|---|---|---|---|---|
| **Claude Sonnet 4.6** | Anthropic | 5/5 (100%) | 40.9s | ~52s | $0.2224 | 5/5 | 5/5 | 5/5 |
| **Claude Haiku 4.5** | Anthropic | 5/5 (100%) | 21.0s | ~26s | $0.0227 | 5/5 | 5/5 | 5/5 |
| **GPT-4o Mini** | OpenAI | 5/5 (100%) | 14.1s | ~16s | $0.0027 | 5/5 | 5/5 | 5/5 |
| **Llama 3.1 70B** | Meta | 4/5 (80%) | 13.9s | ~18s | $0.0087 | 5/5 | 5/5 | 4/5 |
| **Mistral Nemo 12B** | Mistral AI | 4/5 (80%) | 6.4s | 8.6s | $0.0006 | 3/5 | 5/5 | 0/5 |

> **Sections present:** All three required sections — `## Severity`, `## Root Cause Hypothesis`, `## Suggested Actions` — with correct `##` heading level.
> **P-level format:** Must use `P1`/`P2`/`P3`/`P4` — not `High`/`Low`/`Critical`.
> **Log citations:** At least one HDFS timestamp in `## Root Cause Hypothesis` — proves the model read the log.

---

## Per-model results

### Claude Sonnet 4.6  (`anthropic/claude-sonnet-4-6`)

**Provider:** Anthropic  |  **Pass rate:** 5/5 (100%)  |  **Avg $/run:** $0.2224

| Case | Pass | Notes |
|---|---|---|
| case-001 | ✅ | — |
| case-002 | ✅ | — |
| case-003 | ✅ | — |
| case-004 | ✅ | — |
| case-005 | ✅ | — |

**Aggregate:** p50=40.9s  |  p95≈52s  |  ~26K input tokens/case (full log read via multiple `read_log_chunk` calls)

---

### Claude Haiku 4.5  (`anthropic/claude-haiku-4-5`)

**Provider:** Anthropic  |  **Pass rate:** 5/5 (100%)  |  **Avg $/run:** $0.0227

| Case | Pass | Notes |
|---|---|---|
| case-001 | ✅ | — |
| case-002 | ✅ | — |
| case-003 | ✅ | — |
| case-004 | ✅ | — |
| case-005 | ✅ | — |

**Aggregate:** p50=21.0s  |  p95≈26s  |  ~26K input tokens/case

---

### GPT-4o Mini  (`openai/gpt-4o-mini`)

**Provider:** OpenAI  |  **Pass rate:** 5/5 (100%)  |  **Avg $/run:** $0.0027

| Case | Pass | Notes |
|---|---|---|
| case-001 | ✅ | — |
| case-002 | ✅ | — |
| case-003 | ✅ | — |
| case-004 | ✅ | — |
| case-005 | ✅ | — |

**Aggregate:** p50=14.1s  |  p95≈16s  |  **15,647 input tokens on every case (uniform — anomaly)**

> ⚠️ Token anomaly: GPT-4o Mini read exactly 15,647 input tokens on all 5 cases. This strongly suggests it stopped after a single `read_log_chunk` call rather than iterating. Outputs pass the rubric but analysis is shallower than Sonnet/Haiku — no burst-window timing, no per-subnet breakdown.

---

### Llama 3.1 70B  (`meta-llama/llama-3.1-70b-instruct`)

**Provider:** Meta (via OpenRouter)  |  **Pass rate:** 4/5 (80%)  |  **Avg $/run:** $0.0087

| Case | Pass | Notes |
|---|---|---|
| case-001 | ✅ | — |
| case-002 | ✅ | — |
| case-003 | ✅ | — |
| case-004 | ✅ | — |
| case-005 | ❌ | missing: 'WARN' — 298 output tokens; report truncated, verbosity too low |

**Aggregate:** p50=13.9s  |  p95≈18s

---

### Mistral Nemo 12B  (`mistralai/mistral-nemo`)

**Provider:** Mistral AI  |  **Pass rate:** 4/5 (80%)  |  **Avg $/run:** $0.0006

| Case | Pass | Latency | Input tokens | Output tokens | Notes |
|---|---|---|---|---|---|
| case-001 | ✅ | 5.8s | 26,913 | 376 | — |
| case-002 | ✅ | 6.4s | 26,903 | 558 | — |
| case-003 | ✅ | 5.0s | 26,903 | 357 | — |
| case-004 | ❌ | 6.5s | 26,901 | 361 | missing: 'DataXceiver' |
| case-005 | ✅ | 8.6s | 26,899 | 475 | — |

**Total tokens:** 134,519 in / 2,127 out  |  **p50:** 6.4s  |  **p95:** 8.6s

> Note: Replaced `mistralai/mistral-7b-instruct` (deprecated on OpenRouter May 2026) with `mistral-nemo` ($0.02/$0.03 per 1M tokens).

---

## Qualitative observations

Assessed by reading all 25 output files in `experiments/outputs/multi-provider/`.

| Model | Output quality | Structured format | Notable failure modes |
|---|---|---|---|
| **Claude Sonnet 4.6** | Excellent | Yes | None — forensic-level analysis: exact burst timestamps, per-subnet DataNode patterns, thread-pool exhaustion hypothesis, multi-hypothesis ranking, specific remediation shell commands |
| **Claude Haiku 4.5** | Good | Yes | None — solid log citations with exact line references, burst timing identified (21:40–22:40 + 08:10–08:20 waves), concrete `ethtool`/`jstat` commands; shallower than Sonnet but fully actionable |
| **GPT-4o Mini** | Acceptable | Yes | Shallow reading — uniform 15,647 input tokens across all cases points to a single `read_log_chunk` call; cites specific log lines but lacks burst-pattern timing analysis |
| **Llama 3.1 70B** | Acceptable | Yes | Verbosity failures — case-005 output only 298 tokens (truncated, missing WARN evidence); generic action items across other cases ("investigate logs", "verify connectivity") with no specific commands |
| **Mistral Nemo 12B** | Poor | Partial | Header format drift (`###` instead of `##` in case-001); zero HDFS timestamps cited in Root Cause Hypothesis across all cases; vague root cause ("bugs in the software"); no burst-pattern or subnet analysis |

> Quality scale: **Excellent** / **Good** / **Acceptable** / **Poor**
> Format: **Yes** (all 3 sections, correct `##` level) / **Partial** (sections present but wrong heading level in ≥1 case) / **No**

---

## Recommendation

### Production (quality-sensitive — on-call SRE reads this output)

→ **`anthropic/claude-haiku-4-5`** as the default; escalate to **`anthropic/claude-sonnet-4-6`** for P1/P2 incidents.

**Why Haiku as default:** 100% pass rate, correct structured format on every case, solid log citations, and actionable suggested actions with specific shell commands. At $0.023/run it is 10× cheaper than Sonnet and 2.6× cheaper than Llama — with materially better output quality than either open-weight option. For P3/P4 incidents where the SRE needs a fast triage summary, Haiku is the right call.

**Why escalate to Sonnet for P1/P2:** Sonnet's forensic depth — exact burst windows, per-subnet analysis, thread-pool exhaustion reasoning, multi-hypothesis ranking — is worth the $0.22/run when a production incident is causing revenue impact. Haiku's P3 severity assessment on a case Sonnet called P2 is a meaningful signal that Haiku can underestimate blast radius on complex, multi-node failure patterns.

### Dev iteration (cost-optimised — you're tuning prompts)

→ **`openai/gpt-4o-mini`** at $0.0027/run.

At 14s p50 and 100% pass rate, GPT-4o Mini gives the fastest prompt iteration loop. The shallow-reading anomaly doesn't matter when you're testing rubric coverage or section format — it still hits all required substrings. Switch to Haiku or Sonnet for final validation before shipping a prompt change.

### Routing strategy

```
For every incoming log alert:
  1. Run Haiku → get severity P-level + triage report
  2. If severity == P1 or P2:
       Re-run with Sonnet → use Sonnet output for the incident ticket
  3. If severity == P3 or P4:
       Use Haiku output directly
  4. During prompt development:
       Use GPT-4o Mini for all iteration loops
       Run Haiku + Sonnet only for final validation gate
```

**Expected blended cost at 80% P3/P4 and 20% P1/P2:**
`(0.8 × $0.023) + (0.2 × ($0.023 + $0.222))` ≈ **$0.067/run** — 3× Haiku-only cost, but with Sonnet depth where it matters.

---

## Failure mode taxonomy

Failure modes observed across all 5 models during this experiment:

| Failure mode | How to detect | Models affected |
|---|---|---|
| Missing sections | `grep -c "^## " output.md` < 3 | None (all models produced all 3 sections) |
| Header format drift | Uses `### Severity` instead of `## Severity` | Mistral Nemo (case-001 outputs `###`) |
| No log citations | No HDFS timestamps in Root Cause Hypothesis | Mistral Nemo (0/5 cases), Llama 3.1 70B (partial — omitted in short outputs) |
| Generic actions | "Check the logs" / "restart the service" — no specifics | Llama 3.1 70B, Mistral Nemo |
| Severity label non-standard | Uses `High`/`Low` instead of `P1`–`P4` | None (all models used P-level notation) |
| Skipped tool calls / shallow read | Uniform or anomalously low input token count | GPT-4o Mini (15,647 tokens on all 5 cases — stops after one chunk) |
| Truncated output | Report cuts off mid-section; keyword missing | Llama 3.1 70B (case-005: 298 tokens, missing 'WARN'), Mistral Nemo (case-004: missing 'DataXceiver') |

---

## Pricing reference

Prices in USD per 1M tokens as of May 2026. Verify at https://openrouter.ai/models before citing.

| Model | Input $/1M | Output $/1M |
|---|---|---|
| `anthropic/claude-sonnet-4-6` | $3.00 | $15.00 |
| `anthropic/claude-haiku-4-5` | $0.25 | $1.25 |
| `openai/gpt-4o-mini` | $0.15 | $0.60 |
| `meta-llama/llama-3.1-70b-instruct` | $0.52 | $0.75 |
| `mistralai/mistral-nemo` | $0.02 | $0.03 |

---

*Report generated by `run_multi_provider_comparison.py` — 2026-05-20 13:07 UTC | Qualitative observations + recommendations filled in 2026-05-26*
