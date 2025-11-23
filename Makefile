# Makefile for Easy BDD Framework Development
# Usage: make <target>

.PHONY: help install dev-install test lint format type-check security validate clean run

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
	$(PYTHON) -m flake8 easy_bdd/

format:
	@echo "Running black..."
	$(PYTHON) -m black easy_bdd/ tests/
	@echo "Running isort..."
	$(PYTHON) -m isort easy_bdd/ tests/

type-check:
	@echo "Running mypy..."
	$(PYTHON) -m mypy easy_bdd/

security:
	@echo "Running bandit security checks..."
	$(PYTHON) -m bandit -r easy_bdd/ -ll

quality: lint type-check security
	@echo "All quality checks complete!"

# Testing
test:
	$(PYTHON) -m pytest tests/unit/ -v

test-cov:
	$(PYTHON) -m pytest tests/unit/ --cov=easy_bdd --cov-report=html --cov-report=term

validate:
	$(PYTHON) -m easy_bdd validate tests/cases/

# Running tests
run:
	$(PYTHON) -m easy_bdd run tests/cases/

run-tags:
	$(PYTHON) -m easy_bdd run tests/cases/ --tags $(TAGS)

# Metrics & Analytics
metrics-dashboard:
	$(PYTHON) -m easy_bdd.tools.metrics_cli dashboard --days 7

metrics-flaky:
	$(PYTHON) -m easy_bdd.tools.metrics_cli flaky --days 30

metrics-pass-rate:
	$(PYTHON) -m easy_bdd.tools.metrics_cli pass-rate --days 30

metrics-export:
	$(PYTHON) -m easy_bdd.tools.metrics_cli export --output reports/metrics_dashboard.html --format html --days 30

metrics-api:
	@echo "Starting Metrics API on http://localhost:8001"
	@echo "API docs: http://localhost:8001/docs"
	$(PYTHON) -m easy_bdd.core.metrics_api

run-headed:
	$(PYTHON) -m easy_bdd run tests/cases/ --headed

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
	$(PYTHON) -m easy_bdd run tests/cases/dev/simple_test.yaml --headed

# Performance benchmark
benchmark:
	@echo "Running performance benchmark..."
	time $(PYTHON) -m easy_bdd run tests/cases/dev/aws_s3_list_firmware.yaml

# Security validation
sec-validate: security validate
	@echo "Security validation complete!"

# Full CI pipeline
ci: quality test validate
	@echo "CI pipeline complete!"
