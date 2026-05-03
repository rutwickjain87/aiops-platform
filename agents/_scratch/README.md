# `_scratch/` — throwaway experiments

This directory is for **Day 1–2 throwaway code** that helps you feel the agent loop before you commit to architectural patterns. Files here are intentionally rough.

After Day 2, real agents move into named subdirectories (`agents/log-intelligence/`, `agents/k8s-doctor/`, etc.) using the `_templates/agent-skeleton/` pattern from the workspace root.

## What's here

| File | Day | Purpose |
|---|---|---|
| `day1_loop.py` | 1 | Your first ReAct agent — same logic, called via Anthropic SDK and OpenRouter. The point: feel that "the provider is just a config swap." |

## Quick start

```bash
cd ~/workspace/claude-code/ai-journey/agentic-ai-projects/aiops-platform/agents/_scratch
uv venv && source .venv/bin/activate
uv pip install anthropic openai python-dotenv

# Make sure ANTHROPIC_API_KEY and OPENROUTER_API_KEY are in your shell
# (set in ~/.zshrc per SETUP.md)

python day1_loop.py
```

You should see two outputs — one from each provider — both calling `get_current_time()` and producing similar answers.

## When to delete this directory

Day 14+. By then you'll have all your patterns absorbed into real agents and `_scratch/` is just clutter. Until then, keep it — Day-1 you and Day-9 you may want to come back and re-feel the basics.
