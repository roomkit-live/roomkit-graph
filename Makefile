.PHONY: install dev lint lint-fix format typecheck security test test-cov check all clean

install:
	uv sync --prerelease=allow

dev:
	uv sync --extra dev --prerelease=allow

lint:
	uv run ruff check src/ tests/

lint-fix:
	uv run ruff check --fix src/ tests/

format:
	uv run ruff format src/ tests/

format-check:
	uv run ruff format --check src/ tests/

typecheck:
	uv run ty check src/roomkit_graph/

security:
	uv run bandit -r src/ -c pyproject.toml

test:
	uv run pytest -v

test-cov:
	uv run pytest --cov --cov-report=term-missing

check: lint-fix format-check typecheck security

all: check test

clean:
	rm -rf .pytest_cache .mypy_cache .ruff_cache htmlcov dist build
	find src tests -type d -name __pycache__ -exec rm -rf {} +
