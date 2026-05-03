# Security Policy

## Reporting a vulnerability

**Do not open a public issue for security findings.** Email `rutwick.jain87@gmail.com` with:

- A description of the issue
- Steps to reproduce (or a proof-of-concept if safe to share)
- The version / commit SHA you found it on
- Any suggested mitigation

I aim to acknowledge within 72 hours and provide an initial assessment within 7 days. Critical issues will be patched and disclosed within 30 days; lower-severity issues within 90 days.

## Scope

This repo includes agents that interact with cloud APIs, Kubernetes clusters, and external services. Security-relevant areas:

- **Tool dispatch** — any place where LLM output is converted to a side effect
- **MCP servers** in `services/mcp-*` — particularly the Prometheus and kubectl wrappers
- **Approval gates** — the human-in-the-loop checkpoints before mutating actions
- **Sandboxing** — Docker isolation in the SAST auto-fixer (`agents/sast-auto-fix/`)
- **Scope guards** — the IP/network validation in the pentest agent (`agents/pentest-lab/`)

## Out of scope

- The intentionally-vulnerable workloads under `agents/k8s-doctor/test-fixtures/` and the `vulhub` containers used by the pentest agent. Those are vulnerable on purpose.
- Issues that require physical access or social engineering of the maintainer.
- Theoretical attacks without a working PoC.

## Responsible LLM-specific concerns

Prompt injection, tool-call manipulation, and context exfiltration are explicitly in scope. If you find a way to:

- Cause an agent to call a tool with attacker-controlled input
- Cause an agent to leak its system prompt
- Cause an agent to bypass an approval gate

…please report it. These are the highest-priority categories for this repo.

## Acknowledgement

Researchers who responsibly disclose will be credited in `CHANGELOG.md` (with permission) and in the release notes for the patched version.
