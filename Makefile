include .env
export

.PHONY: all

help:
	poetry install
	poetry run python -m metrics --help

install:
	pip install -r requirements.txt

test:
	pytest -v

lint:
	ruff check metrics/ tests/

format:
	ruff format metrics/ tests/

coverage:
	pytest --cov=metrics --cov-report=term-missing

clean:
	rm -rf .pytest_cache .coverage htmlcov output/*.png
