# RAGF Ontology Auditor · Makefile
#
# Conventions:
#   - `up` / `down` manage the ephemeral Neo4j sandbox.
#   - `audit` requires ONTOLOGY=<path>; refuses to run without it (fail-closed).
#   - `wait` blocks until Bolt accepts connections.
#   - All paths are relative to this Makefile.
#
# Python binary:
#   Defaults to `python3`. macOS Sequoia and later, and most Linux distros,
#   ship only `python3` in PATH — `python` does not exist. Override via:
#     make install PYTHON=/path/to/python
#   Tools (pytest, ruff, mypy) are invoked as `$(PYTHON) -m <tool>` so they
#   resolve from the same Python environment regardless of shell PATH.

SHELL := /bin/bash
.ONESHELL:
.SHELLFLAGS := -eu -o pipefail -c
.DEFAULT_GOAL := help

PYTHON          ?= python3
PIP             := $(PYTHON) -m pip

NEO4J_URI       ?= bolt://127.0.0.1:7687
NEO4J_USER      ?= neo4j
NEO4J_PASSWORD  ?= auditor_local_only
ONTOLOGY        ?=
REPORTS_DIR     ?= ./reports

.PHONY: help
help:  ## Show this help
	@awk 'BEGIN {FS = ":.*?## "} /^[a-zA-Z_-]+:.*?## / {printf "  \033[36m%-14s\033[0m %s\n", $$1, $$2}' $(MAKEFILE_LIST)

.PHONY: check-python
check-python:  ## Diagnose the Python binary used by this Makefile
	@if ! command -v $(PYTHON) >/dev/null 2>&1; then \
	  echo "ERROR: '$(PYTHON)' not found in PATH." >&2; \
	  echo "Override with: make <target> PYTHON=/full/path/to/python" >&2; \
	  exit 1; \
	fi
	@echo "PYTHON   : $(PYTHON)"
	@echo "Resolved : $$(command -v $(PYTHON))"
	@$(PYTHON) --version

.PHONY: up
up:  ## Start the ephemeral Neo4j sandbox
	docker compose up -d neo4j-auditor
	@$(MAKE) wait

.PHONY: wait
wait:  ## Block until Neo4j Bolt is reachable
	@echo "Waiting for Neo4j to become healthy..."
	@for i in $$(seq 1 90); do \
	  status=$$(docker inspect -f '{{.State.Health.Status}}' ragf-auditor-neo4j 2>/dev/null || echo "starting"); \
	  if [ "$$status" = "healthy" ]; then echo "Neo4j is healthy."; exit 0; fi; \
	  sleep 1; \
	done; \
	echo "Neo4j did not become healthy in 90s." >&2; exit 1

.PHONY: down
down:  ## Stop and remove the sandbox (data is wiped — tmpfs)
	docker compose down --remove-orphans

.PHONY: audit
audit: check-python  ## Audit an ontology · usage: make audit ONTOLOGY=examples/fintech_minimal.yaml
	@if [ -z "$(ONTOLOGY)" ]; then \
	  echo "ERROR: ONTOLOGY=<path> is required. Example:" >&2; \
	  echo "  make audit ONTOLOGY=examples/fintech_minimal.yaml" >&2; \
	  exit 2; \
	fi
	@if [ ! -f "$(ONTOLOGY)" ]; then \
	  echo "ERROR: ONTOLOGY file not found: $(ONTOLOGY)" >&2; exit 2; \
	fi
	mkdir -p $(REPORTS_DIR)
	NEO4J_URI=$(NEO4J_URI) NEO4J_USER=$(NEO4J_USER) NEO4J_PASSWORD=$(NEO4J_PASSWORD) \
	  $(PYTHON) -m harness_auditor.cli audit \
	    --ontology $(ONTOLOGY) \
	    --reports-dir $(REPORTS_DIR)

.PHONY: install
install: check-python  ## Editable install with dev dependencies
	$(PIP) install -e ".[dev]"

.PHONY: venv
venv: check-python  ## Create an isolated .venv and show how to activate it
	$(PYTHON) -m venv .venv
	@echo
	@echo "Virtual environment created at ./.venv"
	@echo "Activate it with:"
	@echo "  source .venv/bin/activate"
	@echo "Then re-run: make install"

.PHONY: test
test: check-python  ## Run the full test suite
	$(PYTHON) -m pytest -q

.PHONY: test-fast
test-fast: check-python  ## Run only tests that do NOT need a live Neo4j sandbox
	$(PYTHON) -m pytest -q tests/test_schemas.py tests/test_report.py

.PHONY: lint
lint: check-python  ## Lint + type-check
	$(PYTHON) -m ruff check src tests
	$(PYTHON) -m mypy src

.PHONY: clean
clean:  ## Remove reports and Python caches
	rm -rf $(REPORTS_DIR) .pytest_cache .mypy_cache .ruff_cache
	find . -type d -name __pycache__ -prune -exec rm -rf {} +
