# Makefile for Easy BDD Framework Development
# Usage: make <target>

.PHONY: help install dev-install test lint format type-check security validate clean run \
        validate-suite validate-run validate-case debug-run run-testrail run-testrail-id \
        create-run create-run-dry sync-suite push-yaml fix-selectors fix-crawled \
        record-test build-mcpb mcp-serve

# Python executable - use venv if available
PYTHON := $(shell if [ -d ".venv" ]; then echo ".venv/bin/python"; else echo "python"; fi)
PIP := $(shell if [ -d ".venv" ]; then echo ".venv/bin/pip"; else echo "pip"; fi)

# Default target
help:
	@echo "Easy BDD Framework - Development Commands"
	@echo ""
	@echo "Setup:"
	@echo "  make install       - Install package and dependencies"
	@echo "  make dev-install   - Install with development tools"
	@echo "  make hooks         - Install pre-commit hooks"
	@echo ""
	@echo "Code Quality:"
	@echo "  make lint          - Run flake8 linter"
	@echo "  make format        - Format code with black and isort"
	@echo "  make type-check    - Run mypy type checking"
	@echo "  make security      - Run security checks with bandit"
	@echo "  make quality       - Run all quality checks"
	@echo ""
	@echo "Testing:"
	@echo "  make test          - Run unit tests"
	@echo "  make test-cov      - Run tests with coverage"
	@echo "  make validate      - Validate all test files"
	@echo ""
	@echo "Running:"
	@echo "  make run           - Run all tests"
	@echo "  make run-tags      - Run tests with tags (make run-tags TAGS=browser,api)"
	@echo ""
	@echo "Test Builder:"
	@echo "  make builder       - Start Test Builder web application"
	@echo "  make builder-install - Install Test Builder dependencies"
	@echo ""
	@echo "Metrics & Analytics:"
	@echo "  make metrics-dashboard  - Show metrics dashboard (last 7 days)"
	@echo "  make metrics-flaky      - Identify flaky tests (last 30 days)"
	@echo "  make metrics-pass-rate  - Show pass rate trends"
	@echo "  make metrics-export     - Export HTML metrics report"
	@echo "  make metrics-api        - Start metrics REST API server"
	@echo ""
	@echo "Cleanup:"
	@echo "  make clean         - Remove temporary files"
	@echo "  make clean-all     - Remove all generated files"

# Installation
install:
	$(PIP) install -e .

dev-install:
	$(PIP) install -e ".[dev]"
	@echo "Development tools installed!"

hooks:
	$(PYTHON) -m pre_commit install
	@echo "Pre-commit hooks installed!"

# Code Quality
lint:
	@echo "Running flake8..."
	$(PYTHON) -m flake8 easybdd/

format:
	@echo "Running black..."
	$(PYTHON) -m black easybdd/ tests/
	@echo "Running isort..."
	$(PYTHON) -m isort easybdd/ tests/

type-check:
	@echo "Running mypy..."
	$(PYTHON) -m mypy easybdd/

security:
	@echo "Running bandit security checks..."
	$(PYTHON) -m bandit -r easybdd/ -ll

quality: lint type-check security
	@echo "All quality checks complete!"

# Testing
test:
	$(PYTHON) -m pytest tests/unit/ -v

test-cov:
	$(PYTHON) -m pytest tests/unit/ --cov=easybdd --cov-report=html --cov-report=term

validate:
	$(PYTHON) -m easybdd validate tests/cases/

# Running tests
run:
	$(PYTHON) -m easybdd run tests/cases/

run-tags:
	$(PYTHON) -m easybdd run tests/cases/ --tags $(TAGS)

# Metrics & Analytics
metrics-dashboard:
	$(PYTHON) -m easybdd.tools.metrics_cli dashboard --days 7

metrics-flaky:
	$(PYTHON) -m easybdd.tools.metrics_cli flaky --days 30

metrics-pass-rate:
	$(PYTHON) -m easybdd.tools.metrics_cli pass-rate --days 30

metrics-export:
	$(PYTHON) -m easybdd.tools.metrics_cli export --output reports/metrics_dashboard.html --format html --days 30

metrics-api:
	@echo "Starting Metrics API on http://localhost:8001"
	@echo "API docs: http://localhost:8001/docs"
	$(PYTHON) -m easybdd.core.metrics_api

run-headed:
	$(PYTHON) -m easybdd run tests/cases/ --headed

# Cleanup
clean:
	find . -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true
	find . -type f -name "*.pyc" -delete
	find . -type f -name "*.pyo" -delete
	find . -type f -name ".coverage" -delete
	find . -type d -name ".pytest_cache" -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name ".mypy_cache" -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name "htmlcov" -exec rm -rf {} + 2>/dev/null || true

clean-all: clean
	rm -rf build/ dist/ *.egg-info
	rm -rf reports/*.html reports/*.xml
	@echo "All generated files removed!"

# Quick test run
quick-test:
	$(PYTHON) -m easybdd run tests/cases/dev/simple_test.yaml --headed

# Performance benchmark
benchmark:
	@echo "Running performance benchmark..."
	time $(PYTHON) -m easybdd run tests/cases/dev/aws_s3_list_firmware.yaml

# Security validation
sec-validate: security validate
	@echo "Security validation complete!"

# Test Builder Web Application
builder-install:
	@echo "Installing Test Builder dependencies..."
	$(PIP) install -r frontend/requirements_builder.txt
	@echo "Test Builder dependencies installed!"

builder:
	@echo "Starting Test Builder web application..."
	@echo "Access at: http://localhost:8000"
	$(PYTHON) frontend/start_builder.py

# Full CI pipeline
ci: quality test validate
	@echo "CI pipeline complete!"

# =============================================================================
# TEST ENGINEERING — TestRail & Easy BDD workflows
# =============================================================================
#
# Required vars (set on command line):
#   PROJECT=<project_id>   SUITE=<suite_id>   RUN=<run_id>   CASE=<case_id>
#   FILE=<path/to/test.yaml>   TAGS=<tag1,tag2>   URL=<https://...>
#
# Examples:
#   make validate-suite  PROJECT=79 SUITE=106670
#   make debug-run       RUN=194886
#   make run-testrail    PROJECT=79
#   make create-run      PROJECT=79 SUITE=106670 SECTIONS="Functions Firmware"

# Overridable defaults
PROJECT ?=
SUITE   ?=
RUN     ?=
CASE    ?=
FILE    ?=
TAGS    ?=
URL     ?=
NAME    ?=
SECTIONS ?=

help-testrail:
	@echo ""
	@echo "  Easy BDD — TestRail & test engineering targets"
	@echo "  ─────────────────────────────────────────────────────────────────"
	@echo "  VALIDATE"
	@echo "    make validate-suite  PROJECT=xx SUITE=xx   Validate all cases in a suite"
	@echo "    make validate-run    RUN=xx                Validate all cases in a run"
	@echo "    make validate-case   CASE=xx               Validate a single TestRail case"
	@echo ""
	@echo "  DEBUG"
	@echo "    make debug-run       RUN=xx                List failures in a run"
	@echo "    make fix-selectors   FILE=tests/cases/x.yaml   Heal selectors on live page"
	@echo "    make fix-crawled                           Batch-heal all crawled YAML files"
	@echo "    make push-yaml       FILE=x.yaml [CASE=xx] Re-push steps to TestRail"
	@echo ""
	@echo "  RUN"
	@echo "    make run-testrail    PROJECT=xx            Run active EASY_BDD: run"
	@echo "    make run-testrail-id PROJECT=xx RUN=xx     Run a specific TestRail run"
	@echo ""
	@echo "  TESTRAIL"
	@echo "    make create-run    PROJECT=xx SUITE=xx [SECTIONS='F1 F2']  Create a run"
	@echo "    make create-run-dry  (same args)           Dry-run preview"
	@echo "    make sync-suite    PROJECT=xx SUITE=xx     Sync suite → local YAML"
	@echo ""
	@echo "  AUTHORING"
	@echo "    make record-test   [URL=https://...]       Record Playwright → YAML"
	@echo ""
	@echo "  MCP / BUNDLE"
	@echo "    make mcp-serve                             Start MCP server (STDIO)"
	@echo "    make build-mcpb                            Build easy-bdd-<ver>.mcpb"
	@echo ""

# ── Validate ─────────────────────────────────────────────────────────────────
validate-suite:
	@test -n "$(PROJECT)" || (echo "ERROR: set PROJECT=<project_id>"; exit 1)
	@test -n "$(SUITE)"   || (echo "ERROR: set SUITE=<suite_id>"; exit 1)
	$(PYTHON) -m easybdd validate --testrail-suite $(SUITE) --project $(PROJECT)

validate-run:
	@test -n "$(RUN)" || (echo "ERROR: set RUN=<run_id>"; exit 1)
	$(PYTHON) -m easybdd validate --testrail-run $(RUN)

validate-case:
	@test -n "$(CASE)" || (echo "ERROR: set CASE=<case_id>"; exit 1)
	$(PYTHON) -m easybdd validate --testrail-case $(CASE)

# ── Debug ─────────────────────────────────────────────────────────────────────
debug-run:
	@test -n "$(RUN)" || (echo "ERROR: set RUN=<run_id>"; exit 1)
	@echo "=== Failed / Retest cases for run R$(RUN) ===" && \
	$(PYTHON) -c "\
import sys, json; sys.path.insert(0,'.'); \
from easybdd.mcp_server import get_testrail_run_failures; \
data = json.loads(get_testrail_run_failures(run_id=$(RUN))); \
print(f'Total: {data[\"total\"]}  Failures: {data[\"failures\"]}'); \
[print(f'  C{c[\"case_id\"]}  [{c[\"status\"]}]  {c[\"title\"]}  →  {c[\"yaml_hint\"]}') for c in data['cases']] \
"

fix-selectors:
	@test -n "$(FILE)" || (echo "ERROR: set FILE=<path/to/test.yaml>"; exit 1)
	$(PYTHON) -c "\
import sys, json; sys.path.insert(0,'.'); \
from easybdd.mcp_server import fix_test_selectors; \
data = json.loads(fix_test_selectors(path='$(FILE)')); \
print(f'Changes: {len(data[\"changes\"])}  Unfixed: {len(data[\"unfixed\"])}  Saved: {data[\"saved\"]}'); \
[print(f'  Step {c[\"step\"]}: {c[\"old\"]} → {c[\"new\"]}') for c in data['changes']] \
"

fix-crawled:
	$(PYTHON) -c "\
import sys, json; sys.path.insert(0,'.'); \
from easybdd.mcp_server import fix_crawled_tests; \
data = json.loads(fix_crawled_tests()); \
print(f'Processed {data[\"processed\"]} files, total fixes: {sum(f.get(\"changes\",0) for f in data[\"files\"])}') \
"

push-yaml:
	@test -n "$(FILE)" || (echo "ERROR: set FILE=<path/to/test.yaml>"; exit 1)
	$(PYTHON) -c "\
import sys, json; sys.path.insert(0,'.'); \
from easybdd.mcp_server import repush_yaml_to_testrail; \
kw = {'path': '$(FILE)'}$(if $(CASE), | kw.update({'case_id': $(CASE)}),); \
print(json.loads(repush_yaml_to_testrail(**kw))) \
"

# ── Run ──────────────────────────────────────────────────────────────────────
run-testrail:
	@test -n "$(PROJECT)" || (echo "ERROR: set PROJECT=<project_id>"; exit 1)
	$(PYTHON) -m easybdd testrail-run $(PROJECT)

run-testrail-id:
	@test -n "$(PROJECT)" || (echo "ERROR: set PROJECT=<project_id>"; exit 1)
	@test -n "$(RUN)"     || (echo "ERROR: set RUN=<run_id>"; exit 1)
	$(PYTHON) -m easybdd testrail-run $(PROJECT) --run-id $(RUN)

# ── TestRail ─────────────────────────────────────────────────────────────────
create-run:
	@test -n "$(PROJECT)" || (echo "ERROR: set PROJECT=<project_id>"; exit 1)
	@test -n "$(SUITE)"   || (echo "ERROR: set SUITE=<suite_id>"; exit 1)
	$(PYTHON) -m easybdd testrail-create-run $(PROJECT) $(SUITE) \
	    $(if $(SECTIONS),--sections $(SECTIONS),) \
	    $(if $(NAME),--name "$(NAME)",)

create-run-dry:
	@test -n "$(PROJECT)" || (echo "ERROR: set PROJECT=<project_id>"; exit 1)
	@test -n "$(SUITE)"   || (echo "ERROR: set SUITE=<suite_id>"; exit 1)
	$(PYTHON) -m easybdd testrail-create-run $(PROJECT) $(SUITE) \
	    $(if $(SECTIONS),--sections $(SECTIONS),) --dry-run

sync-suite:
	@test -n "$(PROJECT)" || (echo "ERROR: set PROJECT=<project_id>"; exit 1)
	@test -n "$(SUITE)"   || (echo "ERROR: set SUITE=<suite_id>"; exit 1)
	$(PYTHON) -m easybdd testrail-sync $(PROJECT) --suite $(SUITE)

# ── Authoring ────────────────────────────────────────────────────────────────
record-test:
	$(PYTHON) -m easybdd record $(URL) \
	    $(if $(NAME),--name "$(NAME)",) \
	    $(if $(PROJECT),--testrail-project $(PROJECT),) \
	    $(if $(SUITE),--testrail-suite $(SUITE),)

# ── MCP / Bundle ─────────────────────────────────────────────────────────────
mcp-serve:
	$(PYTHON) -m easybdd mcp-serve

build-mcpb:
	$(PYTHON) build_mcpb.py
