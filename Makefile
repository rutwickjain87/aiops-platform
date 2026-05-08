# aiops-platform — top-level Makefile
#
# Usage:
#   make eval                    # run eval suite (Anthropic backend, threshold 80%)
#   make eval THRESHOLD=1.0      # stricter threshold
#   make eval BACKEND=langchain  # different backend
#   make test                    # run unit tests
#   make lint                    # ruff check + format check
#   make fmt                     # auto-fix formatting

AGENT_DIR   := agents/log-intelligence
VENV        := $(AGENT_DIR)/.venv
PYTHON      := $(VENV)/bin/python
UV          := uv

THRESHOLD   ?= 0.80
BACKEND     ?= anthropic
RESULTS_DIR := evals/results

.PHONY: eval test lint fmt setup help

# ── eval ──────────────────────────────────────────────────────────────────────
# Runs the agent eval suite and writes evals/results/latest.json.
# Exits non-zero if pass rate < THRESHOLD.
eval:
	@mkdir -p $(RESULTS_DIR)
	@echo "Running eval (backend=$(BACKEND), threshold=$(THRESHOLD))..."
	cd $(AGENT_DIR) && $(PYTHON) -m pytest_runner 2>/dev/null || true
	cd $(AGENT_DIR) && $(PYTHON) ../../scripts/run_eval_ci.py \
	    --backend $(BACKEND) \
	    --threshold $(THRESHOLD) \
	    --output ../../$(RESULTS_DIR)/latest.json

# ── test ──────────────────────────────────────────────────────────────────────
test:
	@echo "Running unit tests..."
	$(VENV)/bin/pytest tests/ -v \
	    --cov=agents \
	    --cov=services \
	    --cov-report=term-missing \
	    --cov-report=html:htmlcov

# ── lint ──────────────────────────────────────────────────────────────────────
lint:
	$(VENV)/bin/ruff check .
	$(VENV)/bin/ruff format --check .

# ── fmt ───────────────────────────────────────────────────────────────────────
fmt:
	$(VENV)/bin/ruff check --fix .
	$(VENV)/bin/ruff format .

# ── setup ─────────────────────────────────────────────────────────────────────
# Bootstrap the agent venv (run once after clone)
setup:
	cd $(AGENT_DIR) && $(UV) venv && $(UV) pip install -r requirements_anthropic.txt
	$(UV) venv && $(UV) pip install -r requirements.txt

# ── help ──────────────────────────────────────────────────────────────────────
help:
	@echo ""
	@echo "  make eval            Run agent eval suite (Anthropic backend)"
	@echo "  make eval BACKEND=langchain  Run with LangChain backend"
	@echo "  make eval THRESHOLD=1.0      Require 100% pass rate"
	@echo "  make test            Run unit tests with coverage"
	@echo "  make lint            Ruff lint + format check"
	@echo "  make fmt             Auto-fix lint + format"
	@echo "  make setup           Bootstrap venvs after first clone"
	@echo ""
