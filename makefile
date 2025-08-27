.PHONY: help install build test test-fast test-slow test-unit test-integration test-contracts format lint type-check clean shell dev docs coverage benchmark watch-tests install-dev update-deps check-poetry

# Colors for output
RED=\033[0;31m
GREEN=\033[0;32m
YELLOW=\033[1;33m
BLUE=\033[0;34m
NC=\033[0m # No Color

# Default target
help:
	@echo "$(BLUE)Available commands:$(NC)"
	@echo ""
	@echo "$(GREEN)Setup & Installation:$(NC)"
	@echo "  install        - Install dependencies with Poetry"
	@echo "  install-dev    - Install with dev dependencies"
	@echo "  shell          - Activate Poetry shell"
	@echo "  update-deps    - Update all dependencies"
	@echo "  check-poetry   - Check if Poetry is installed"
	@echo ""
	@echo "$(GREEN)Building:$(NC)"
	@echo "  build          - Compile all OpShin contracts"
	@echo "  build-contracts- Build contracts with verbose output"
	@echo ""
	@echo "$(GREEN)Testing:$(NC)"
	@echo "  test           - Run all tests"
	@echo "  test-fast      - Run fast tests only (exclude slow/performance)"
	@echo "  test-slow      - Run slow/performance tests only"
	@echo "  test-unit      - Run unit tests only"
	@echo "  test-integration - Run integration tests only"
	@echo "  test-contracts - Test contract compilation and validation"
	@echo "  coverage       - Run tests with coverage report"
	@echo "  benchmark      - Run performance benchmarks"
	@echo "  watch-tests    - Run tests in watch mode (requires pytest-watch)"
	@echo ""
	@echo "$(GREEN)Code Quality:$(NC)"
	@echo "  format         - Format code with black and isort"
	@echo "  lint           - Run all linting checks"
	@echo "  type-check     - Run type checking with mypy only"
	@echo ""
	@echo "$(GREEN)Maintenance:$(NC)"
	@echo "  clean          - Clean build artifacts and cache"
	@echo "  clean-deep     - Deep clean including Poetry cache"
	@echo "  docs           - Build documentation"
	@echo ""
	@echo "$(GREEN)Workflows:$(NC)"
	@echo "  dev            - Complete development workflow"
	@echo "  ci             - Run CI/CD pipeline locally"
	@echo "  pre-commit     - Run pre-commit checks"
	@echo "  release-check  - Check if ready for release"

# Setup & Installation
check-poetry:
	@which poetry > /dev/null || (echo "$(RED)Poetry not installed. Install it first: https://python-poetry.org/docs/#installation$(NC)" && exit 1)
	@echo "$(GREEN)✓ Poetry is installed$(NC)"

install: check-poetry
	@echo "$(BLUE)Installing dependencies...$(NC)"
	poetry install
	@echo "$(GREEN)✓ Dependencies installed$(NC)"

install-dev: check-poetry
	@echo "$(BLUE)Installing with dev dependencies...$(NC)"
	poetry install --with dev
	@echo "$(GREEN)✓ Dev dependencies installed$(NC)"

update-deps: check-poetry
	@echo "$(BLUE)Updating dependencies...$(NC)"
	poetry update
	@echo "$(GREEN)✓ Dependencies updated$(NC)"

shell: check-poetry
	@echo "$(BLUE)Activating Poetry shell...$(NC)"
	poetry shell

# Building
build: check-poetry
	@echo "$(BLUE)Compiling OpShin contracts...$(NC)"
	poetry run python src/scripts/build_contracts.py
	@echo "$(GREEN)✓ Contracts compiled$(NC)"

build-contracts: check-poetry
	@echo "$(BLUE)Building contracts with verbose output...$(NC)"
	poetry run python src/scripts/build_contracts.py --verbose
	@echo "$(GREEN)✓ Contracts built successfully$(NC)"

# Testing
test: check-poetry
	@echo "$(BLUE)Running all tests...$(NC)"
	poetry run pytest -v
	@echo "$(GREEN)✓ All tests completed$(NC)"

test-fast: check-poetry
	@echo "$(BLUE)Running fast tests...$(NC)"
	poetry run pytest -v -m "not slow and not integration"
	@echo "$(GREEN)✓ Fast tests completed$(NC)"

test-slow: check-poetry
	@echo "$(BLUE)Running slow/performance tests...$(NC)"
	poetry run pytest -v -m "slow"
	@echo "$(GREEN)✓ Slow tests completed$(NC)"

test-unit: check-poetry
	@echo "$(BLUE)Running unit tests...$(NC)"
	poetry run pytest -v -m "unit"
	@echo "$(GREEN)✓ Unit tests completed$(NC)"

test-integration: check-poetry
	@echo "$(BLUE)Running integration tests...$(NC)"
	poetry run pytest -v -m "integration"
	@echo "$(GREEN)✓ Integration tests completed$(NC)"

test-contracts: build
	@echo "$(BLUE)Testing contract compilation and validation...$(NC)"
	poetry run pytest -v tests/test_contract_compilation.py
	@echo "$(GREEN)✓ Contract tests completed$(NC)"

coverage: check-poetry
	@echo "$(BLUE)Running tests with coverage...$(NC)"
	poetry run pytest --cov=src --cov-report=html --cov-report=term-missing --cov-report=xml
	@echo "$(GREEN)✓ Coverage report generated in htmlcov/index.html$(NC)"

benchmark: check-poetry
	@echo "$(BLUE)Running performance benchmarks...$(NC)"
	poetry run pytest --benchmark-only -v
	@echo "$(GREEN)✓ Benchmarks completed$(NC)"

watch-tests: check-poetry
	@echo "$(BLUE)Starting test watch mode...$(NC)"
	@echo "$(YELLOW)Press Ctrl+C to stop$(NC)"
	poetry run ptw -- -v

# Code Quality
format: check-poetry
	@echo "$(BLUE)Formatting code...$(NC)"
	poetry run black .
	poetry run isort .
	@echo "$(GREEN)✓ Code formatted$(NC)"

type-check: check-poetry
	@echo "$(BLUE)Running type checking...$(NC)"
	poetry run mypy src
	@echo "$(GREEN)✓ Type checking completed$(NC)"

lint: check-poetry format type-check
	@echo "$(BLUE)Running all linting checks...$(NC)"
	@if poetry run which flake8 >/dev/null 2>&1; then \
		poetry run flake8 src tests; \
	else \
		echo "$(YELLOW)⚠ flake8 not installed, skipping$(NC)"; \
	fi
	@echo "$(GREEN)✓ All linting checks passed$(NC)"

# Documentation
docs: check-poetry
	@echo "$(BLUE)Building documentation...$(NC)"
	poetry run sphinx-build -b html docs docs/_build/html
	@echo "$(GREEN)✓ Documentation built in docs/_build/html/index.html$(NC)"

# Maintenance
clean:
	@echo "$(BLUE)Cleaning build artifacts...$(NC)"
	rm -rf artifacts/
	rm -rf build/
	rm -rf dist/
	rm -rf *.egg-info/
	rm -rf __pycache__/
	rm -rf .pytest_cache/
	rm -rf .mypy_cache/
	rm -rf .coverage
	rm -rf htmlcov/
	rm -rf docs/_build/
	find . -name "*.pyc" -delete
	find . -name "*.pyo" -delete
	find . -name "*.pyd" -delete
	find . -name "__pycache__" -type d -exec rm -rf {} +
	@echo "$(GREEN)✓ Cleaned build artifacts$(NC)"

clean-deep: clean
	@echo "$(BLUE)Deep cleaning including Poetry cache...$(NC)"
	poetry cache clear --all pypi
	@echo "$(GREEN)✓ Deep clean completed$(NC)"

# Workflows
dev: install format lint test-fast build
	@echo "$(GREEN)✓ Development workflow completed successfully!$(NC)"

ci: install lint type-check test coverage build
	@echo "$(GREEN)✓ CI pipeline completed successfully!$(NC)"

pre-commit: format lint test-fast
	@echo "$(GREEN)✓ Pre-commit checks completed!$(NC)"

release-check: clean install lint type-check test coverage build docs
	@echo "$(GREEN)✓ Release checks completed successfully!$(NC)"
	@echo "$(BLUE)Ready for release!$(NC)"

# Advanced Testing Options
test-verbose: check-poetry
	@echo "$(BLUE)Running tests with maximum verbosity...$(NC)"
	poetry run pytest -vv -s

test-debug: check-poetry
	@echo "$(BLUE)Running tests in debug mode...$(NC)"
	poetry run pytest -vv -s --pdb

test-failed: check-poetry
	@echo "$(BLUE)Running only previously failed tests...$(NC)"
	poetry run pytest --lf -v

test-parallel: check-poetry
	@echo "$(BLUE)Running tests in parallel...$(NC)"
	poetry run pytest -n auto -v

# Contract-specific commands
validate-contracts: build
	@echo "$(BLUE)Validating compiled contracts...$(NC)"
	poetry run python src/scripts/validate_contracts.py
	@echo "$(GREEN)✓ Contracts validated$(NC)"

contract-sizes: build
	@echo "$(BLUE)Checking contract sizes...$(NC)"
	poetry run python src/scripts/contract_sizes.py
	@echo "$(GREEN)✓ Contract sizes checked$(NC)"

# Development utilities
install-hooks: check-poetry
	@echo "$(BLUE)Installing pre-commit hooks...$(NC)"
	poetry run pre-commit install
	@echo "$(GREEN)✓ Pre-commit hooks installed$(NC)"

update-hooks: check-poetry
	@echo "$(BLUE)Updating pre-commit hooks...$(NC)"
	poetry run pre-commit autoupdate
	@echo "$(GREEN)✓ Pre-commit hooks updated$(NC)"

# Environment info
env-info: check-poetry
	@echo "$(BLUE)Environment Information:$(NC)"
	@echo "Poetry version: $$(poetry --version)"
	@echo "Python version: $$(poetry run python --version)"
	@echo "Virtual env: $$(poetry env info --path)"
	@poetry run pip list | head -20

# Database/Node commands (customize for your setup)
start-node:
	@echo "$(BLUE)Starting Cardano node...$(NC)"
	# Add your node start command here
	# cardano-node run --config config.json

stop-node:
	@echo "$(BLUE)Stopping Cardano node...$(NC)"
	# pkill cardano-node

# Quick aliases for common tasks
t: test-fast
b: build
f: format
l: lint
c: clean
i: install

# Help for aliases
aliases:
	@echo "$(BLUE)Quick aliases:$(NC)"
	@echo "  t  - test-fast"
	@echo "  b  - build"  
	@echo "  f  - format"
	@echo "  l  - lint"
	@echo "  c  - clean"
	@echo "  i  - install"

# Project status
status: env-info
	@echo ""
	@echo "$(BLUE)Project Status:$(NC)"
	@echo "Git status:"
	@git status --porcelain | head -10 || echo "Not a git repository"
	@echo ""
	@echo "Recent commits:"
	@git log --oneline -5 || echo "No git history"

# Advanced development commands
fix-imports: check-poetry
	@echo "$(BLUE)Fixing import order...$(NC)"
	poetry run isort . --diff
	poetry run isort .
	@echo "$(GREEN)✓ Imports fixed$(NC)"

check-deps: check-poetry
	@echo "$(BLUE)Checking for dependency issues...$(NC)"
	poetry check
	poetry run pip check
	@echo "$(GREEN)✓ Dependencies are consistent$(NC)"

security-check: check-poetry
	@echo "$(BLUE)Running security checks...$(NC)"
	poetry run safety check
	@echo "$(GREEN)✓ Security check completed$(NC)"

# Performance profiling
profile-tests: check-poetry
	@echo "$(BLUE)Profiling test performance...$(NC)"
	poetry run pytest --durations=10
	@echo "$(GREEN)✓ Test profiling completed$(NC)"

memory-profile: check-poetry
	@echo "$(BLUE)Running memory profiling...$(NC)"
	poetry run python -m memory_profiler tests/test_performance.py
	@echo "$(GREEN)✓ Memory profiling completed$(NC)"

# Example integration with external tools
docker-test:
	@echo "$(BLUE)Running tests in Docker...$(NC)"
	docker-compose run --rm app make test
	@echo "$(GREEN)✓ Docker tests completed$(NC)"

docker-build:
	@echo "$(BLUE)Building Docker image...$(NC)"
	docker-compose build
	@echo "$(GREEN)✓ Docker image built$(NC)"

# Network-specific testing (customize for your needs)
test-mainnet: check-poetry
	@echo "$(BLUE)Running mainnet tests...$(NC)"
	NETWORK=mainnet poetry run pytest tests/test_network_specific.py
	@echo "$(GREEN)✓ Mainnet tests completed$(NC)"

test-testnet: check-poetry
	@echo "$(BLUE)Running testnet tests...$(NC)"
	NETWORK=testnet poetry run pytest tests/test_network_specific.py  
	@echo "$(GREEN)✓ Testnet tests completed$(NC)"

# Project maintenance
outdated: check-poetry
	@echo "$(BLUE)Checking for outdated dependencies...$(NC)"
	poetry show --outdated

upgrade-deps: check-poetry
	@echo "$(BLUE)Upgrading dependencies...$(NC)"
	poetry update
	@echo "$(GREEN)✓ Dependencies upgraded$(NC)"

# Backup and restore
backup-artifacts:
	@echo "$(BLUE)Backing up build artifacts...$(NC)"
	tar -czf artifacts-backup-$$(date +%Y%m%d-%H%M%S).tar.gz artifacts/ || echo "No artifacts to backup"
	@echo "$(GREEN)✓ Artifacts backed up$(NC)"