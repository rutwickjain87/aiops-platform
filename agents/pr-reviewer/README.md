# PR Security Reviewer (Day 4)

An AI-powered GitHub PR security reviewer built on the LangChain + Claude ReAct loop.

## What it does

On every pull request the agent:

1. **Fetches the PR diff** via PyGithub (`fetch_pr_diff`)
2. **Runs Semgrep SAST** on each changed code file (`run_semgrep`)
3. **Reasons** over the diff + SAST findings to catch what static analysis misses (hardcoded secrets, injection patterns, logic flaws, missing auth)
4. **Posts a structured review comment** to the PR — idempotent, so re-runs update the same comment instead of spamming the timeline (`post_review_comment`)

## New concepts (vs Day 2 log triage)

| Day 2 — Log Triage | Day 4 — PR Security Review |
|---|---|
| File I/O tools | GitHub API tool (PyGithub) |
| Heuristic clustering | SAST integration (Semgrep) |
| Free-text triage report | Structured JSON + Markdown output |
| Standalone CLI | GitHub Actions CI trigger |
| Stateless per-run | Idempotent comment update |

## Setup

```bash
cd agents/pr-reviewer
uv venv && source .venv/bin/activate
uv pip install -r requirements.txt

export ANTHROPIC_API_KEY=sk-ant-...
export GITHUB_TOKEN=ghp_...
```

## Usage

```bash
# Dry-run (print review to stdout only)
python reviewer.py --repo rutwickjain87/aiops-platform --pr 7

# Post the review as a PR comment (creates or updates the bot comment)
python reviewer.py --repo rutwickjain87/aiops-platform --pr 7 --post-comment

# Use Sonnet for higher-fidelity review
python reviewer.py --repo rutwickjain87/aiops-platform --pr 7 --model claude-sonnet-4-6
```

## GitHub Actions integration

The workflow at `.github/workflows/ai-review.yml` runs automatically on every PR.  
Secrets required in your repository settings:

| Secret | Description |
|--------|-------------|
| `ANTHROPIC_API_KEY` | Anthropic API key |
| `GITHUB_TOKEN` | Automatically provided by Actions |

## Output format

```
## 🔒 AI Security Review

**Summary:** 2 HIGH findings require immediate remediation.

### Findings

| # | File | Line | Severity | CWE | Issue |
|---|------|------|----------|-----|-------|
| 1 | `db.py` | 14 | 🔴 HIGH | CWE-89 | SQL injection via f-string interpolation |
| 2 | `config.py` | 3 | 🔴 HIGH | CWE-798 | Hardcoded AWS secret key |

### Details
...
```

## Idempotency

Every comment written by the bot contains the hidden marker `<!-- ai-reviewer:v1 -->`.  
On push to an existing PR, the bot finds the marker and edits its comment in-place — one comment, always current.

## Architecture

```
reviewer.py          ← CLI (argparse)
  └── planner.py     ← LangChain ReAct loop (bind_tools + explicit iteration)
        └── tools.py ← @tool functions: fetch_pr_diff, run_semgrep, post_review_comment
```
