# RAGF Ontology Auditor · Makefile
#
# Conventions:
#   - `up` / `down` manage the ephemeral Neo4j sandbox.
#   - `audit` requires ONTOLOGY=<path>; refuses to run without it (fail-closed).
#   - `wait` blocks until Bolt accepts connections.
#   - `notebook-test` and the integration tests require a live sandbox; the
#     `_check-bolt-up` helper gives them a fast, friendly diagnostic when
#     the container is down (instead of a 60-line neo4j traceback).
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

# Private helper (underscore-prefixed → hidden from `make help`). Probes
# Bolt with a short-timeout TCP connect and prints an actionable message
# when the sandbox is not up. Targets that need a live sandbox depend on
# this so the user gets one clear line instead of a stacktrace.
.PHONY: _check-bolt-up
_check-bolt-up:
	@if ! $(PYTHON) -c "import socket; s=socket.socket(); s.settimeout(2); s.connect(('127.0.0.1', 7687)); s.close()" >/dev/null 2>&1; then \
	  echo "ERROR: Neo4j sandbox is not reachable at bolt://127.0.0.1:7687." >&2; \
	  echo "  Start it first with:  make up" >&2; \
	  echo "  Then re-run the target you wanted (e.g. make notebook-test)." >&2; \
	  exit 3; \
	fi

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

.PHONY: notebook-test
notebook-test: check-python _check-bolt-up  ## Headless-execute the demo notebook (requires .[notebook] + a live sandbox)
	@if ! $(PYTHON) -c "import nbconvert" >/dev/null 2>&1; then \
	  echo "ERROR: notebook extras not installed." >&2; \
	  echo "  Install with: $(PIP) install -e \".[notebook]\"" >&2; \
	  exit 2; \
	fi
	$(PYTHON) -m jupyter nbconvert --to notebook --execute \
	  notebooks/01_quickstart.ipynb --output /tmp/01_quickstart_executed.ipynb
	@rm -f /tmp/01_quickstart_executed.ipynb
	@echo "Notebook executed cleanly."

.PHONY: clean
clean:  ## Remove reports and Python caches
	rm -rf $(REPORTS_DIR) .pytest_cache .mypy_cache .ruff_cache
	find . -type d -name __pycache__ -prune -exec rm -rf {} +
