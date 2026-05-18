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
#   make setup-k8s-doctor        # bootstrap k8s-doctor venv only
#   make cluster-up              # create kind cluster + deploy broken fixtures
#   make cluster-down            # delete kind cluster
#   make run-k8s-doctor          # diagnose CrashLoopBackOff in doctor-lab
#   make test-k8s-doctor         # run k8s-doctor unit tests
#   make setup-mcp-prometheus    # bootstrap mcp-prometheus venv only
#   make run-mcp-prometheus      # start Prometheus MCP server (stdio)
#   make eval-k8s-doctor         # run offline eval suite (no cluster required)
#   make routing-experiment      # run model routing experiment (ON vs OFF)
#   make setup-sast-fix          # bootstrap sast-auto-fix venv only
#   make scan-sast               # scan target with Semgrep (no fix)
#   make run-sast-fix            # scan + fix + validate + open PR
#   make setup-alert-correlator  # bootstrap alert-correlator venv only
#   make correlator-up           # start pgvector Docker container
#   make correlator-down         # stop pgvector Docker container
#   make correlate               # run alert correlator (synthetic mixed scenario)
#   make correlate SCENARIO=oom_cascade    # specific scenario
#   make setup-incident-commander         # bootstrap incident-commander venv only
#   make respond-demo            # run incident commander with demo OOM incident
#   make respond-demo DEMO=node_pressure  # different demo scenario
#   make respond                          # full pipeline: correlate → incident commander
#   make respond SCENARIO=oom_cascade     # full pipeline with specific scenario

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

K8S_AGENT_DIR   := agents/k8s-doctor
K8S_VENV        := $(K8S_AGENT_DIR)/.venv
K8S_PYTHON      := $(K8S_VENV)/bin/python
K8S_PYTEST      := $(K8S_VENV)/bin/pytest
K8S_PYTHON_ABS  := $(CURDIR)/$(K8S_VENV)/bin/python

MCP_PROM_DIR    := services/mcp-prometheus
MCP_PROM_VENV   := $(MCP_PROM_DIR)/.venv
MCP_PROM_PYTHON_ABS := $(CURDIR)/$(MCP_PROM_VENV)/bin/python

SAST_AGENT_DIR  := agents/sast-auto-fix
SAST_VENV       := $(SAST_AGENT_DIR)/.venv
SAST_PYTHON_ABS := $(CURDIR)/$(SAST_VENV)/bin/python

IAC_AGENT_DIR   := agents/iac-generator
IAC_VENV        := $(IAC_AGENT_DIR)/.venv
IAC_PYTHON_ABS  := $(CURDIR)/$(IAC_VENV)/bin/python
IAC_PROMPT      ?= "A containerised web app on AWS ECS Fargate with an ALB and a Postgres RDS database"
IAC_OUTPUT      ?= $(IAC_AGENT_DIR)/iac-output

CORR_AGENT_DIR  := agents/alert-correlator
CORR_VENV       := $(CORR_AGENT_DIR)/.venv
CORR_PYTHON_ABS := $(CURDIR)/$(CORR_VENV)/bin/python
SCENARIO        ?= mixed

INC_AGENT_DIR   := agents/incident-commander
INC_VENV        := $(INC_AGENT_DIR)/.venv
INC_PYTHON_ABS  := $(CURDIR)/$(INC_VENV)/bin/python
DEMO            ?= oom

K8S_NAMESPACE   ?= doctor-lab
K8S_RESOURCE    ?= crashloop-demo
K8S_SYMPTOM     ?= CrashLoopBackOff
K8S_CONTEXT     ?= kind-doctor-lab

UV              := uv

THRESHOLD       ?= 0.80
BACKEND         ?= anthropic
RESULTS_DIR     := evals/results

.PHONY: eval test test-log test-slack-bot test-pr-reviewer test-k8s-doctor lint fmt \
        setup setup-log setup-slack-bot setup-pr-reviewer setup-k8s-doctor setup-mcp-prometheus \
        setup-sast-fix setup-iac-gen setup-alert-correlator setup-incident-commander \
        obs-up obs-down obs-logs run-slack-bot run-pr-reviewer \
        cluster-up cluster-down run-k8s-doctor run-mcp-prometheus \
        eval-k8s-doctor routing-experiment scan-sast run-sast-fix \
        run-iac-gen run-iac-gen-no-validate \
        correlator-up correlator-down correlate respond-demo respond help

.DEFAULT_GOAL := help

# ── setup ─────────────────────────────────────────────────────────────────────
# Bootstrap all agent venvs (run once after clone or after pulling new deps)
setup: setup-log setup-slack-bot setup-pr-reviewer setup-k8s-doctor setup-mcp-prometheus

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

setup-k8s-doctor:
	@echo "Setting up k8s-doctor venv..."
	cd $(K8S_AGENT_DIR) && $(UV) venv .venv && $(UV) pip install -r requirements.txt --python .venv/bin/python
	@echo "K8s Doctor venv ready at $(K8S_VENV)"

setup-mcp-prometheus:
	@echo "Setting up mcp-prometheus venv..."
	cd $(MCP_PROM_DIR) && $(UV) venv .venv && $(UV) pip install -r requirements.txt --python .venv/bin/python
	@echo "MCP Prometheus venv ready at $(MCP_PROM_VENV)"

# ── test ──────────────────────────────────────────────────────────────────────
# Runs all unit tests across all agents.
# Each agent uses its own venv so deps stay isolated.
test: test-log test-slack-bot test-k8s-doctor

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

# ── k8s-doctor ────────────────────────────────────────────────────────────────
# Requires: kind installed + make setup-k8s-doctor run first.

cluster-up:
	@echo "Creating kind cluster 'doctor-lab'..."
	kind create cluster --name doctor-lab 2>/dev/null || echo "Cluster already exists"
	@echo "Deploying broken fixtures..."
	kubectl apply -f $(K8S_AGENT_DIR)/fixtures/crashloop.yaml --context kind-doctor-lab
	kubectl apply -f $(K8S_AGENT_DIR)/fixtures/imagepull.yaml --context kind-doctor-lab
	@echo ""
	@echo "  Wait ~30s then check:"
	@echo "  kubectl get pods -n doctor-lab --context kind-doctor-lab"

cluster-down:
	@echo "Deleting kind cluster 'doctor-lab'..."
	kind delete cluster --name doctor-lab

test-k8s-doctor:
	@if [ ! -f "$(K8S_PYTEST)" ]; then \
	    echo "⚠️  k8s-doctor venv not found — run: make setup-k8s-doctor"; \
	    exit 1; \
	fi
	@echo "Running k8s-doctor tests..."
	cd $(K8S_AGENT_DIR) && $(K8S_PYTHON_ABS) -m pytest tests/ -v

run-k8s-doctor:
	@if [ ! -f "$(K8S_PYTHON_ABS)" ]; then \
	    echo "⚠️  k8s-doctor venv not found — run: make setup-k8s-doctor"; \
	    exit 1; \
	fi
	@echo "Running K8s Doctor (namespace=$(K8S_NAMESPACE) resource=$(K8S_RESOURCE))"
	cd $(K8S_AGENT_DIR) && \
	    $(K8S_PYTHON_ABS) doctor.py \
	        --namespace $(K8S_NAMESPACE) \
	        --resource $(K8S_RESOURCE) \
	        --symptom "$(K8S_SYMPTOM)" \
	        --context $(K8S_CONTEXT)

run-mcp-prometheus:
	@if [ ! -f "$(MCP_PROM_PYTHON_ABS)" ]; then \
	    echo "⚠️  mcp-prometheus venv not found — run: make setup-mcp-prometheus"; \
	    exit 1; \
	fi
	@echo "Starting Prometheus MCP server (stdio)..."
	cd $(MCP_PROM_DIR) && $(MCP_PROM_PYTHON_ABS) server.py

eval-k8s-doctor:
	@if [ ! -f "$(K8S_PYTEST)" ]; then \
	    echo "⚠️  k8s-doctor venv not found — run: make setup-k8s-doctor"; \
	    exit 1; \
	fi
	@echo "Running K8s Doctor offline eval (no live cluster required)..."
	cd $(K8S_AGENT_DIR) && $(K8S_PYTHON_ABS) evals/run_eval.py

routing-experiment:
	@if [ ! -f "$(K8S_PYTEST)" ]; then \
	    echo "⚠️  k8s-doctor venv not found — run: make setup-k8s-doctor"; \
	    exit 1; \
	fi
	@echo "Running K8s Doctor model routing experiment (routing ON vs OFF)..."
	cd $(K8S_AGENT_DIR) && $(K8S_PYTHON_ABS) evals/run_routing_experiment.py

setup-sast-fix:
	@echo "Setting up sast-auto-fix venv..."
	cd $(SAST_AGENT_DIR) && $(UV) venv .venv && $(UV) pip install -r requirements.txt --python .venv/bin/python
	@echo "SAST Auto-Fixer venv ready at $(SAST_VENV)"

scan-sast:
	@if [ ! -f "$(SAST_PYTHON_ABS)" ]; then \
	    echo "⚠️  sast-auto-fix venv not found — run: make setup-sast-fix"; \
	    exit 1; \
	fi
	@echo "Scanning target with Semgrep (no fix)..."
	cd $(SAST_AGENT_DIR) && $(SAST_PYTHON_ABS) auto_fix.py --scan-only

run-sast-fix:
	@if [ ! -f "$(SAST_PYTHON_ABS)" ]; then \
	    echo "⚠️  sast-auto-fix venv not found — run: make setup-sast-fix"; \
	    exit 1; \
	fi
	@echo "Running SAST Auto-Fixer (scan → fix → validate → PR)..."
	cd $(SAST_AGENT_DIR) && $(SAST_PYTHON_ABS) auto_fix.py

# ── IaC Generator ─────────────────────────────────────────────────────────────
setup-iac-gen:
	@echo "Setting up iac-generator venv..."
	cd $(IAC_AGENT_DIR) && python3 -m venv .venv
	cd $(IAC_AGENT_DIR) && $(IAC_PYTHON_ABS) -m pip install --quiet --upgrade pip
	cd $(IAC_AGENT_DIR) && $(IAC_PYTHON_ABS) -m pip install --quiet -r requirements.txt
	@echo "✅  iac-generator venv ready. Copy .env.example → .env and fill in ANTHROPIC_API_KEY"

run-iac-gen:
	@if [ ! -f "$(IAC_PYTHON_ABS)" ]; then \
	    echo "⚠️  iac-generator venv not found — run: make setup-iac-gen"; \
	    exit 1; \
	fi
	@echo "Running IaC Generator (clarify → plan → generate → validate)..."
	cd $(IAC_AGENT_DIR) && $(IAC_PYTHON_ABS) generate.py $(IAC_PROMPT) --output $(IAC_OUTPUT)

run-iac-gen-no-validate:
	@if [ ! -f "$(IAC_PYTHON_ABS)" ]; then \
	    echo "⚠️  iac-generator venv not found — run: make setup-iac-gen"; \
	    exit 1; \
	fi
	@echo "Running IaC Generator (no terraform validate)..."
	cd $(IAC_AGENT_DIR) && $(IAC_PYTHON_ABS) generate.py $(IAC_PROMPT) --output $(IAC_OUTPUT) --no-validate

# ── Alert Correlator ──────────────────────────────────────────────────────────
setup-alert-correlator:
	@echo "Setting up alert-correlator venv..."
	cd $(CORR_AGENT_DIR) && python3 -m venv .venv
	cd $(CORR_AGENT_DIR) && $(CORR_PYTHON_ABS) -m pip install --quiet --upgrade pip
	cd $(CORR_AGENT_DIR) && $(CORR_PYTHON_ABS) -m pip install --quiet -r requirements.txt
	@echo "✅  alert-correlator venv ready. Copy .env.example → .env (no Voyage AI key needed — embeddings are local)"

correlator-up:
	@echo "Starting pgvector container..."
	docker compose -f $(CORR_AGENT_DIR)/docker-compose.yml up -d
	@echo "  pgvector listening on localhost:5432 (db=alerts, user=alertcorr)"
	@echo "  Wait ~5s for healthcheck, then run: make correlate"

correlator-down:
	docker compose -f $(CORR_AGENT_DIR)/docker-compose.yml down

correlate:
	@if [ ! -f "$(CORR_PYTHON_ABS)" ]; then \
	    echo "⚠️  alert-correlator venv not found — run: make setup-alert-correlator"; \
	    exit 1; \
	fi
	@echo "Running Alert Correlator (scenario=$(SCENARIO))..."
	cd $(CORR_AGENT_DIR) && $(CORR_PYTHON_ABS) correlate.py --scenario $(SCENARIO)

# ── Incident Commander ─────────────────────────────────────────────────────────
setup-incident-commander:
	@echo "Setting up incident-commander venv..."
	cd $(INC_AGENT_DIR) && python3 -m venv .venv
	cd $(INC_AGENT_DIR) && $(INC_PYTHON_ABS) -m pip install --quiet --upgrade pip
	cd $(INC_AGENT_DIR) && $(INC_PYTHON_ABS) -m pip install --quiet -r requirements.txt
	@echo "✅  incident-commander venv ready. Copy .env.example → .env and fill in keys"

respond-demo:
	@if [ ! -f "$(INC_PYTHON_ABS)" ]; then \
	    echo "⚠️  incident-commander venv not found — run: make setup-incident-commander"; \
	    exit 1; \
	fi
	@echo "Running Incident Commander demo (scenario=$(DEMO))..."
	cd $(INC_AGENT_DIR) && $(INC_PYTHON_ABS) respond.py --demo $(DEMO)

# ── Full pipeline: Alert Correlator → Incident Commander ──────────────────────
# Correlates alerts from a synthetic scenario, saves incidents to a temp file,
# then hands them straight to the Incident Commander.
PIPELINE_TMPFILE ?= /tmp/aiops-incidents.json

respond:
	@if [ ! -f "$(CORR_PYTHON_ABS)" ]; then \
	    echo "⚠️  alert-correlator venv not found — run: make setup-alert-correlator"; \
	    exit 1; \
	fi
	@if [ ! -f "$(INC_PYTHON_ABS)" ]; then \
	    echo "⚠️  incident-commander venv not found — run: make setup-incident-commander"; \
	    exit 1; \
	fi
	@echo "━━━ Step 1/2: Alert Correlator (scenario=$(SCENARIO)) ━━━"
	cd $(CORR_AGENT_DIR) && $(CORR_PYTHON_ABS) correlate.py --scenario $(SCENARIO) --output $(PIPELINE_TMPFILE)
	@if [ ! -s "$(PIPELINE_TMPFILE)" ]; then \
	    echo "No incidents produced — nothing to hand to Incident Commander."; \
	    exit 0; \
	fi
	@echo ""
	@echo "━━━ Step 2/2: Incident Commander ━━━"
	cd $(INC_AGENT_DIR) && $(INC_PYTHON_ABS) respond.py --incident $(PIPELINE_TMPFILE)

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
	@echo "  make setup-slack-bot         Bootstrap slack-incident-bot venv only"
	@echo "  make setup-pr-reviewer       Bootstrap pr-reviewer venv only"
	@echo "  make setup-k8s-doctor        Bootstrap k8s-doctor venv only"
	@echo "  make setup-mcp-prometheus    Bootstrap mcp-prometheus venv only"
	@echo "  make cluster-up              Create kind cluster + deploy broken fixtures"
	@echo "  make cluster-down            Delete kind cluster"
	@echo "  make run-k8s-doctor          Diagnose CrashLoopBackOff in doctor-lab"
	@echo "  make eval-k8s-doctor         Run offline eval suite (no cluster required)"
	@echo "  make routing-experiment      Run model routing experiment (ON vs OFF)"
	@echo ""
	@echo "  Testing"
	@echo "  ─────────────────────────────────────────────────────────────"
	@echo "  make test            Run ALL unit tests (all agents)"
	@echo "  make test-log        Run log-intelligence tests only"
	@echo "  make test-slack-bot          Run slack-incident-bot tests only"
	@echo "  make test-k8s-doctor         Run k8s-doctor tests only"
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
