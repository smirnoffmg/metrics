include .env
export

.PHONY: all

help:
	uv run python -m metrics --help

install:
	uv sync

test:
	uv run pytest -v

lint:
	uv run ruff check metrics/ tests/

format:
	uv run ruff format metrics/ tests/

coverage:
	uv run pytest --cov=metrics --cov-report=term-missing

clean:
	rm -rf .pytest_cache .coverage htmlcov output/*.png
