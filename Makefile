help:
	poetry install
	poetry run python -m metrics --help

test:
	poetry run pytest --cov=metrics --cov-report=term-missing:skip-covered tests/

lint:
	pre-commit run --all
