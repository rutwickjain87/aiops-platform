# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added
- Initial scaffolding for AIOps platform repo
- Standard agent skeleton (planner / tools / memory / evaluator)
- Architecture documentation in `architecture/system-design.md`
- Postmortem example in `docs/postmortems/incident-001.md`

### Changed
- _Nothing yet_

### Fixed
- _Nothing yet_

---

## [0.1.0] — Phase 1 complete (planned for Day 11)

> The first public release. Targets end of the 11-day Phase 1 build.

### Added
- 8 working agents across 3 flagship domains:
  - **Log Intelligence:** Log Triage, Alert Correlator
  - **K8s Doctor:** OpenSRE-extended troubleshooter, Self-Healing loop
  - **Incident Commander:** 4-agent CrewAI orchestrator
- Plus supporting agents: PR Security Reviewer, Slack Incident Bot, SAST Auto-Fixer, IaC Generator, Pentest Lab Agent
- Custom MCP server for Prometheus
- LangSmith tracing across all agents
- Prometheus metrics exporter
- Eval suite with ≥80% pass rate across the platform
- Demo gifs for the 3 flagships
- Cost/quality experiment comparing Ollama vs Sonnet vs Haiku
- micro-SaaS skeleton (`saas/`) wrapping the IaC Generator

### Notes
- First merged PR contributed back to [Tracer-Cloud/opensre](https://github.com/Tracer-Cloud/opensre)
- All synthetic metrics labeled as such

---

[Unreleased]: https://github.com/<your-username>/aiops-platform/compare/v0.1.0...HEAD
[0.1.0]: https://github.com/<your-username>/aiops-platform/releases/tag/v0.1.0
