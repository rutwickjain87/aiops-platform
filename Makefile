# aiops-platform — top-level Makefile
#
# Usage:
#   make                     # show this help (default)
#   make setup               # bootstrap all venvs (run once after clone)
#   make setup-log           # bootstrap log-intelligence venv only
#   make setup-bot           # bootstrap slack-incident-bot venv only
#   make test                # run ALL unit tests (all agents)
#   make test-log            # run log-intelligence tests only
#   make test-bot            # run slack-incident-bot tests only (24 tests)
#   make eval                # run eval suite (Anthropic backend, threshold 80%)
#   make eval THRESHOLD=1.0  # stricter threshold
#   make eval BACKEND=langchain
#   make lint                # ruff check + format check
#   make fmt                 # auto-fix formatting

# ── Venv paths ────────────────────────────────────────────────────────────────
LOG_AGENT_DIR   := agents/log-intelligence
LOG_VENV        := $(LOG_AGENT_DIR)/.venv
LOG_PYTHON      := $(LOG_VENV)/bin/python
LOG_PYTEST      := $(LOG_VENV)/bin/pytest

BOT_AGENT_DIR   := agents/slack-incident-bot
BOT_VENV        := $(BOT_AGENT_DIR)/.venv
BOT_PYTHON      := $(BOT_VENV)/bin/python
BOT_PYTEST      := $(BOT_VENV)/bin/pytest

UV              := uv

THRESHOLD       ?= 0.80
BACKEND         ?= anthropic
RESULTS_DIR     := evals/results

.PHONY: eval test test-log test-bot lint fmt setup setup-log setup-bot help

.DEFAULT_GOAL := help

# ── setup ─────────────────────────────────────────────────────────────────────
# Bootstrap all agent venvs (run once after clone or after pulling new deps)
setup: setup-log setup-bot

setup-log:
	@echo "Setting up log-intelligence venv..."
	cd $(LOG_AGENT_DIR) && $(UV) venv .venv && $(UV) pip install -r requirements_anthropic.txt --python .venv/bin/python

setup-bot:
	@echo "Setting up slack-incident-bot venv..."
	cd $(BOT_AGENT_DIR) && $(UV) venv .venv && $(UV) pip install -r requirements.txt --python .venv/bin/python
	@echo "Bot venv ready at $(BOT_VENV)"

# ── test ──────────────────────────────────────────────────────────────────────
# Runs all unit tests across all agents.
# Each agent uses its own venv so deps stay isolated.
test: test-log test-bot

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

test-bot:
	@if [ ! -f "$(BOT_PYTEST)" ]; then \
	    echo "⚠️  slack-incident-bot venv not found — run: make setup-bot"; \
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
	@echo "  make setup-bot       Bootstrap slack-incident-bot venv only"
	@echo ""
	@echo "  Testing"
	@echo "  ─────────────────────────────────────────────────────────────"
	@echo "  make test            Run ALL unit tests (all agents)"
	@echo "  make test-log        Run log-intelligence tests only"
	@echo "  make test-bot        Run slack-incident-bot tests only (24 tests)"
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
