.PHONY: install build test format lint clean help

# Default target
help:
	@echo "Available commands:"
	@echo "  install  - Install dependencies with Poetry"
	@echo "  build    - Compile all OpShin contracts"
	@echo "  test     - Run tests"
	@echo "  format   - Format code with black and isort"
	@echo "  lint     - Run type checking with mypy"
	@echo "  clean    - Clean build artifacts"
	@echo "  shell    - Activate Poetry shell"

install:
	poetry install

build:
	poetry run python src/scripts/build_contracts.py

test:
	poetry run pytest

format:
	poetry run black .
	poetry run isort .

lint:
	poetry run mypy .

clean:
	rm -rf artifacts/
	rm -rf __pycache__/
	rm -rf .pytest_cache/
	find . -name "*.pyc" -delete
	find . -name "*.pyo" -delete

shell:
	poetry shell

# Development workflow
dev: install format lint test build