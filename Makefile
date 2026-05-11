# aiops-platform — top-level Makefile
#
# Usage:
#   make                         # show this help (default)
#   make setup                   # bootstrap all venvs (run once after clone)
#   make setup-log               # bootstrap log-intelligence venv only
#   make setup-slack-bot         # bootstrap slack-incident-bot venv only
#   make setup-pr-reviewer       # bootstrap pr-reviewer venv only
#   make test                    # run ALL unit tests (all agents)
#   make test-log                # run log-intelligence tests only
#   make test-slack-bot          # run slack-incident-bot tests only
#   make eval                    # run eval suite (Anthropic backend, threshold 80%)
#   make eval THRESHOLD=1.0      # stricter threshold
#   make eval BACKEND=langchain
#   make lint                    # ruff check + format check
#   make fmt                     # auto-fix formatting
#   make obs-up                  # start Prometheus + Loki + Grafana stack
#   make obs-down                # stop observability stack
#   make obs-logs                # tail observability container logs
#   make run-slack-bot           # run bot and stream JSON logs → logs/slack-incident-bot.log
#   make run-pr-reviewer         # run pr-reviewer → logs/pr-reviewer.log

# ── Venv paths ────────────────────────────────────────────────────────────────
LOG_AGENT_DIR   := agents/log-intelligence
LOG_VENV        := $(LOG_AGENT_DIR)/.venv
LOG_PYTHON      := $(LOG_VENV)/bin/python
LOG_PYTEST      := $(LOG_VENV)/bin/pytest

BOT_AGENT_DIR   := agents/slack-incident-bot
BOT_VENV        := $(BOT_AGENT_DIR)/.venv
BOT_PYTHON      := $(BOT_VENV)/bin/python
BOT_PYTEST      := $(BOT_VENV)/bin/pytest
BOT_PYTHON_ABS  := $(CURDIR)/$(BOT_VENV)/bin/python

PR_AGENT_DIR    := agents/pr-reviewer
PR_VENV         := $(PR_AGENT_DIR)/.venv
PR_PYTHON       := $(PR_VENV)/bin/python
PR_PYTEST       := $(PR_VENV)/bin/pytest
PR_PYTHON_ABS   := $(CURDIR)/$(PR_VENV)/bin/python

UV              := uv

THRESHOLD       ?= 0.80
BACKEND         ?= anthropic
RESULTS_DIR     := evals/results

.PHONY: eval test test-log test-slack-bot test-pr-reviewer lint fmt \
        setup setup-log setup-slack-bot setup-pr-reviewer \
        obs-up obs-down obs-logs run-slack-bot run-pr-reviewer help

.DEFAULT_GOAL := help

# ── setup ─────────────────────────────────────────────────────────────────────
# Bootstrap all agent venvs (run once after clone or after pulling new deps)
setup: setup-log setup-slack-bot setup-pr-reviewer

setup-log:
	@echo "Setting up log-intelligence venv..."
	cd $(LOG_AGENT_DIR) && $(UV) venv .venv && $(UV) pip install -r requirements_anthropic.txt --python .venv/bin/python

setup-slack-bot:
	@echo "Setting up slack-incident-bot venv..."
	cd $(BOT_AGENT_DIR) && $(UV) venv .venv && $(UV) pip install -r requirements.txt --python .venv/bin/python
	@echo "Slack bot venv ready at $(BOT_VENV)"

setup-pr-reviewer:
	@echo "Setting up pr-reviewer venv..."
	cd $(PR_AGENT_DIR) && $(UV) venv .venv && $(UV) pip install -r requirements.txt --python .venv/bin/python
	@echo "PR reviewer venv ready at $(PR_VENV)"

# ── test ──────────────────────────────────────────────────────────────────────
# Runs all unit tests across all agents.
# Each agent uses its own venv so deps stay isolated.
test: test-log test-slack-bot

test-log:
	@if [ ! -f "$(LOG_PYTEST)" ]; then \
	    echo "⚠️  log-intelligence venv not found — run: make setup-log"; \
	    exit 1; \
	fi
	@echo "Running log-intelligence tests..."
	$(LOG_PYTEST) tests/ -v \
	    --cov=agents \
	    --cov=services \
	    --cov-report=term-missing \
	    --cov-report=html:htmlcov \
	    --ignore=tests/test_slack_bot.py

test-slack-bot:
	@if [ ! -f "$(BOT_PYTEST)" ]; then \
	    echo "⚠️  slack-incident-bot venv not found — run: make setup-slack-bot"; \
	    exit 1; \
	fi
	@echo "Running slack-incident-bot tests..."
	$(BOT_PYTEST) tests/test_slack_bot.py -v

# ── eval ──────────────────────────────────────────────────────────────────────
eval:
	@mkdir -p $(RESULTS_DIR)
	@echo "Running eval (backend=$(BACKEND), threshold=$(THRESHOLD))..."
	cd $(LOG_AGENT_DIR) && $(LOG_PYTHON) -m pytest_runner 2>/dev/null || true
	cd $(LOG_AGENT_DIR) && $(LOG_PYTHON) ../../scripts/run_eval_ci.py \
	    --backend $(BACKEND) \
	    --threshold $(THRESHOLD) \
	    --output ../../$(RESULTS_DIR)/latest.json

# ── observability stack ───────────────────────────────────────────────────────
# Starts Prometheus + Loki + Promtail + Grafana via Docker Compose.
# Requires Docker Desktop to be running.
obs-up:
	@echo "Starting observability stack (Prometheus + Loki + Grafana)..."
	@mkdir -p logs
	docker compose -f observability/docker-compose.yml up -d
	@echo ""
	@echo "  Grafana   → http://localhost:3000  (admin / aiops)"
	@echo "  Prometheus → http://localhost:9090"
	@echo "  Loki      → http://localhost:3100"
	@echo ""
	@echo "  Start an agent to ship metrics and logs:"
	@echo "  make run-slack-bot       # bot metrics on :8000, logs → logs/slack-incident-bot.log"
	@echo "  make run-pr-reviewer     # reviewer metrics on :8001, logs → logs/pr-reviewer.log"

obs-down:
	docker compose -f observability/docker-compose.yml down

obs-logs:
	docker compose -f observability/docker-compose.yml logs -f

# ── agent runners (with log file output for Promtail) ─────────────────────────
# Run agents and tee stdout to logs/ so Promtail can pick them up.
# Set ALERT_ID or REPO/PR env vars to customise the trigger.

ALERT_ID  ?= ALERT-001
PR_REPO   ?= owner/repo
PR_NUMBER ?= 1

run-slack-bot:
	@if [ ! -f "$(BOT_VENV)/bin/python" ]; then \
	    echo "⚠️  slack-incident-bot venv not found — run: make setup-slack-bot"; \
	    exit 1; \
	fi
	@mkdir -p logs
	@echo "Starting slack-incident-bot (trigger=$(ALERT_ID)) — logs → logs/slack-incident-bot.log"
	cd $(BOT_AGENT_DIR) && \
	    METRICS_ENABLED=true METRICS_PORT=8000 \
	    .venv/bin/python bot.py --trigger $(ALERT_ID) 2>&1 | tee ../../logs/slack-incident-bot.log

run-pr-reviewer:
	@if [ ! -f "$(PR_PYTHON_ABS)" ]; then \
	    echo "⚠️  pr-reviewer venv not found — run: make setup-pr-reviewer"; \
	    exit 1; \
	fi
	@mkdir -p logs
	@echo "Starting pr-reviewer (repo=$(PR_REPO) pr=$(PR_NUMBER)) — logs → logs/pr-reviewer.log"
	cd $(PR_AGENT_DIR) && \
	    METRICS_ENABLED=true METRICS_PORT=8001 \
	    $(PR_PYTHON_ABS) reviewer.py --repo $(PR_REPO) --pr $(PR_NUMBER) 2>&1 | tee ../../logs/pr-reviewer.log

# ── lint ──────────────────────────────────────────────────────────────────────
lint:
	$(LOG_VENV)/bin/ruff check .
	$(LOG_VENV)/bin/ruff format --check .

# ── fmt ───────────────────────────────────────────────────────────────────────
fmt:
	$(LOG_VENV)/bin/ruff check --fix .
	$(LOG_VENV)/bin/ruff format .

# ── help ──────────────────────────────────────────────────────────────────────
help:
	@echo ""
	@echo "  Setup"
	@echo "  ─────────────────────────────────────────────────────────────"
	@echo "  make setup           Bootstrap all agent venvs (run after clone)"
	@echo "  make setup-log       Bootstrap log-intelligence venv only"
	@echo "  make setup-slack-bot     Bootstrap slack-incident-bot venv only"
	@echo "  make setup-pr-reviewer   Bootstrap pr-reviewer venv only"
	@echo ""
	@echo "  Testing"
	@echo "  ─────────────────────────────────────────────────────────────"
	@echo "  make test            Run ALL unit tests (all agents)"
	@echo "  make test-log        Run log-intelligence tests only"
	@echo "  make test-slack-bot      Run slack-incident-bot tests only"
	@echo ""
	@echo "  Evaluation"
	@echo "  ─────────────────────────────────────────────────────────────"
	@echo "  make eval            Run agent eval suite (Anthropic backend, 80% threshold)"
	@echo "  make eval BACKEND=langchain    Run with LangChain backend"
	@echo "  make eval THRESHOLD=1.0        Require 100% pass rate"
	@echo ""
	@echo "  Code quality"
	@echo "  ─────────────────────────────────────────────────────────────"
	@echo "  make lint            Ruff lint + format check"
	@echo "  make fmt             Auto-fix lint + format"
	@echo ""
