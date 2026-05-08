# Contributing to aiops-platform

Thanks for your interest. This is an actively maintained portfolio + research repo. Contributions are welcome at all sizes — typo fixes through architectural changes.

## Quick start for contributors

```bash
git clone https://github.com/<your-username>/aiops-platform
cd aiops-platform
uv venv && source .venv/bin/activate
uv pip install -r requirements_anthropic.txt  # or requirements_langchain.txt for LangChain backend
cp .env.example .env  # fill in API keys
make test
make eval
```

If `make test` and `make eval` both pass, you're set up.

## Development workflow

1. **Open an issue first** for anything more than a typo. Describe what you want to change and why.
2. **Branch from `main`:** `git checkout -b feat/your-change` (use `feat/`, `fix/`, `docs/`, `chore/` prefixes).
3. **Make focused commits.** One logical change per commit. We squash-merge, but readable commit history is still valuable during review.
4. **Run the eval suite locally:** `make eval`. PRs that drop the eval pass rate are blocked at merge.
5. **Open a PR.** Fill in the PR template completely — especially the "eval impact" and "screenshots/traces" sections.
6. **Expect review.** I aim to respond within 72 hours.

## What makes a good PR

- **Small.** A 200-line PR gets merged; a 2000-line PR sits for weeks.
- **Single-purpose.** Don't bundle a refactor with a feature. Open two PRs.
- **Has an eval delta.** If you changed an agent or prompt, show the eval pass-rate before/after.
- **Has a trace.** If you changed agent behavior, link to a LangSmith trace from the new behavior.
- **Updates the changelog.** Add a line to `CHANGELOG.md` under `[Unreleased]`.
- **Tested.** New code has unit tests; new agent behaviors have eval cases.

## Code style

- **Python:** `ruff format` and `ruff check` (run `make lint`).
- **Type hints:** mandatory on public functions; encouraged elsewhere.
- **Docstrings:** required on tools, planners, and any function that touches an LLM.
- **Tools must be Pydantic-typed:** Pydantic in, Pydantic out. Tools never read the system prompt.

## Agent design conventions

This repo follows the standard agent skeleton (see `_templates/agent-skeleton/` in the parent workspace, or the existing agents for examples):

```
agent/
├── triage.py (or main.py)     # Entry point; --backend anthropic|langchain|openrouter
├── planner_anthropic.py       # Anthropic SDK brain: manual stop_reason loop
├── tools_anthropic.py         # Tools: Pydantic _registry, Anthropic input_schema format
├── memory_anthropic.py        # list[dict] message history (Anthropic SDK only)
├── planner_langchain.py       # LangChain: ChatAnthropic.bind_tools + explicit loop
├── planner_openrouter.py      # OpenRouter: openai.OpenAI(base_url=openrouter.ai/api/v1)
├── tools_openrouter.py        # Tools: same _registry, OpenAI function-calling schema
├── memory_openrouter.py       # Flat messages list with system as first entry
├── evaluator.py               # Validates outputs against ground truth (backend-agnostic)
├── requirements_anthropic.txt # anthropic, pydantic
├── requirements_langchain.txt # langchain, langchain-anthropic, pydantic
└── requirements_openrouter.txt # openai, pydantic
```

Not every agent needs all three backends. Include the ones that add learning value for the day. If you're adding a new agent, follow this structure. If you're modifying an existing one, don't drift from it — open an issue to discuss before introducing a new pattern.

## Reporting bugs

Use `.github/ISSUE_TEMPLATE/bug_report.md`. Include:
- What you expected vs. what happened
- The agent + tool + LangSmith trace (if applicable)
- Reproducer (commands + minimal input)
- Cost/latency if relevant

## Reporting security issues

**Do not open a public issue for security findings.** See [`SECURITY.md`](SECURITY.md).

## Code of Conduct

This project follows the [Contributor Covenant](CODE_OF_CONDUCT.md). By participating, you agree to abide by its terms.
