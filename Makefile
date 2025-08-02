.PHONY: all

VENV_DIR ?= .venv
PYTHON = $(VENV_DIR)/bin/python
PIP = $(VENV_DIR)/bin/pip

all: help

help:
	@echo "Usage: make [target]"
	@echo ""
	@echo "Targets:"
	@echo "  install    - Create a virtual environment and install dependencies"
	@echo "  lint       - Lint the code"
	@echo "  format     - Format the code"
	@echo "  test       - Run tests"
	@echo "  coverage   - Run tests and show coverage"
	@echo "  run        - Run the metrics CLI"
	@echo "  clean      - Clean up generated files"


install:
	@if [ ! -d "$(VENV_DIR)" ]; then \
		echo ">>> Creating virtual environment..."; \
		python3 -m venv $(VENV_DIR); \
	fi
	@echo ">>> Installing dependencies..."
	$(PIP) install -U pip uv
	@echo ">>> Syncing dependencies..."
	@$(VENV_DIR)/bin/uv sync --all-extras

lint:
	@echo ">>> Linting code..."
	@uv run ruff check --fix metrics/ tests/

format:
	@echo ">>> Formatting code..."
	@uv run ruff format metrics/ tests/

test:
	@echo ">>> Running tests..."
	@uv run pytest -v

coverage:
	@echo ">>> Running tests with coverage..."
	@uv run pytest --cov=metrics --cov-report=term-missing

run:
	@uv run python -m metrics

clean:
	@echo ">>> Cleaning up..."
	rm -rf .pytest_cache .coverage htmlcov output/*.png .venv
