.PHONY: help install build test test-fast test-slow test-unit test-integration test-contracts format lint type-check clean shell dev docs coverage benchmark watch-tests install-dev update-deps check-uv

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
	@echo "  install        - Install dependencies with uv"
	@echo "  install-dev    - Install with dev dependencies"
	@echo "  shell          - Activate virtual environment"
	@echo "  update-deps    - Update all dependencies"
	@echo "  check-uv       - Check if uv is installed"
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
check-uv:
	@which uv > /dev/null || (echo "$(RED)uv not installed. Install it first: curl -LsSf https://astral.sh/uv/install.sh | sh$(NC)" && exit 1)
	@echo "$(GREEN)✓ uv is installed$(NC)"

install: check-uv
	@echo "$(BLUE)Installing dependencies...$(NC)"
	uv sync
	@echo "$(GREEN)✓ Dependencies installed$(NC)"

install-dev: check-uv
	@echo "$(BLUE)Installing with dev dependencies...$(NC)"
	uv sync --extra dev
	@echo "$(GREEN)✓ Dev dependencies installed$(NC)"

update-deps: check-uv
	@echo "$(BLUE)Updating dependencies...$(NC)"
	uv lock --upgrade
	uv sync
	@echo "$(GREEN)✓ Dependencies updated$(NC)"

shell:
	@echo "$(BLUE)Activating virtual environment...$(NC)"
	@echo "$(YELLOW)Run: source .venv/bin/activate$(NC)"

# Building
build: check-uv
	@echo "$(BLUE)Compiling OpShin contracts...$(NC)"
	uv run python src/scripts/build_contracts.py
	@echo "$(GREEN)✓ Contracts compiled$(NC)"

build-contracts: check-uv
	@echo "$(BLUE)Building contracts with verbose output...$(NC)"
	uv run python src/scripts/build_contracts.py --verbose
	@echo "$(GREEN)✓ Contracts built successfully$(NC)"

# Testing
test: check-uv
	@echo "$(BLUE)Running all tests...$(NC)"
	uv run pytest -v
	@echo "$(GREEN)✓ All tests completed$(NC)"

test-fast: check-uv
	@echo "$(BLUE)Running fast tests...$(NC)"
	uv run pytest -v -m "not slow and not integration"
	@echo "$(GREEN)✓ Fast tests completed$(NC)"

test-slow: check-uv
	@echo "$(BLUE)Running slow/performance tests...$(NC)"
	uv run pytest -v -m "slow"
	@echo "$(GREEN)✓ Slow tests completed$(NC)"

test-unit: check-uv
	@echo "$(BLUE)Running unit tests...$(NC)"
	uv run pytest -v -m "unit"
	@echo "$(GREEN)✓ Unit tests completed$(NC)"

test-integration: check-uv
	@echo "$(BLUE)Running integration tests...$(NC)"
	uv run pytest -v -m "integration"
	@echo "$(GREEN)✓ Integration tests completed$(NC)"

test-contracts: build
	@echo "$(BLUE)Testing contract compilation and validation...$(NC)"
	uv run pytest -v tests/test_contract_compilation.py
	@echo "$(GREEN)✓ Contract tests completed$(NC)"

coverage: check-uv
	@echo "$(BLUE)Running tests with coverage...$(NC)"
	uv run pytest --cov=src --cov-report=html --cov-report=term-missing --cov-report=xml
	@echo "$(GREEN)✓ Coverage report generated in htmlcov/index.html$(NC)"

benchmark: check-uv
	@echo "$(BLUE)Running performance benchmarks...$(NC)"
	uv run pytest --benchmark-only -v
	@echo "$(GREEN)✓ Benchmarks completed$(NC)"

watch-tests: check-uv
	@echo "$(BLUE)Starting test watch mode...$(NC)"
	@echo "$(YELLOW)Press Ctrl+C to stop$(NC)"
	uv run ptw -- -v

# Code Quality
format: check-uv
	@echo "$(BLUE)Formatting code...$(NC)"
	uv run ruff format .
	uv run ruff check --select I --fix .
	@echo "$(GREEN)✓ Code formatted$(NC)"

type-check: check-uv
	@echo "$(BLUE)Running type checking...$(NC)"
	uv run mypy
	@echo "$(GREEN)✓ Type checking completed$(NC)"

lint: check-uv format type-check
	@echo "$(BLUE)Running all linting checks...$(NC)"
	uv run ruff check .
	@echo "$(GREEN)✓ All linting checks passed$(NC)"

lint-fix: check-uv
	@echo "$(BLUE)Running linting with auto-fixes...$(NC)"
	uv run ruff check --fix .
	uv run ruff format .
	@echo "$(GREEN)✓ Linting fixes applied$(NC)"

# Documentation
docs: check-uv
	@echo "$(BLUE)Building documentation...$(NC)"
	uv run sphinx-build -b html docs docs/_build/html
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
	@echo "$(BLUE)Deep cleaning including uv cache...$(NC)"
	uv cache clean
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
test-verbose: check-uv
	@echo "$(BLUE)Running tests with maximum verbosity...$(NC)"
	uv run pytest -vv -s

test-debug: check-uv
	@echo "$(BLUE)Running tests in debug mode...$(NC)"
	uv run pytest -vv -s --pdb

test-failed: check-uv
	@echo "$(BLUE)Running only previously failed tests...$(NC)"
	uv run pytest --lf -v

test-parallel: check-uv
	@echo "$(BLUE)Running tests in parallel...$(NC)"
	uv run pytest -n auto -v

# Contract-specific commands
validate-contracts: build
	@echo "$(BLUE)Validating compiled contracts...$(NC)"
	uv run python src/scripts/validate_contracts.py
	@echo "$(GREEN)✓ Contracts validated$(NC)"

contract-sizes: build
	@echo "$(BLUE)Checking contract sizes...$(NC)"
	uv run python src/scripts/contract_sizes.py
	@echo "$(GREEN)✓ Contract sizes checked$(NC)"

# Development utilities
install-hooks: check-uv
	@echo "$(BLUE)Installing pre-commit hooks...$(NC)"
	uv run pre-commit install
	@echo "$(GREEN)✓ Pre-commit hooks installed$(NC)"

update-hooks: check-uv
	@echo "$(BLUE)Updating pre-commit hooks...$(NC)"
	uv run pre-commit autoupdate
	@echo "$(GREEN)✓ Pre-commit hooks updated$(NC)"

# Environment info
env-info: check-uv
	@echo "$(BLUE)Environment Information:$(NC)"
	@echo "uv version: $$(uv --version)"
	@echo "Python version: $$(uv run python --version)"
	@echo "Virtual env: $$(pwd)/.venv"
	@uv pip list | head -20

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
fix-imports: check-uv
	@echo "$(BLUE)Fixing import order...$(NC)"
	uv run ruff check --select I --fix .
	@echo "$(GREEN)✓ Imports fixed$(NC)"

check-deps: check-uv
	@echo "$(BLUE)Checking for dependency issues...$(NC)"
	uv pip check
	@echo "$(GREEN)✓ Dependencies are consistent$(NC)"

security-check: check-uv
	@echo "$(BLUE)Running security checks...$(NC)"
	uv run safety check
	@echo "$(GREEN)✓ Security check completed$(NC)"

# Performance profiling
profile-tests: check-uv
	@echo "$(BLUE)Profiling test performance...$(NC)"
	uv run pytest --durations=10
	@echo "$(GREEN)✓ Test profiling completed$(NC)"

memory-profile: check-uv
	@echo "$(BLUE)Running memory profiling...$(NC)"
	uv run python -m memory_profiler tests/test_performance.py
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
test-mainnet: check-uv
	@echo "$(BLUE)Running mainnet tests...$(NC)"
	NETWORK=mainnet uv run pytest tests/test_network_specific.py
	@echo "$(GREEN)✓ Mainnet tests completed$(NC)"

test-testnet: check-uv
	@echo "$(BLUE)Running testnet tests...$(NC)"
	NETWORK=testnet uv run pytest tests/test_network_specific.py
	@echo "$(GREEN)✓ Testnet tests completed$(NC)"

# Project maintenance
outdated: check-uv
	@echo "$(BLUE)Checking for outdated dependencies...$(NC)"
	uv pip list --outdated

upgrade-deps: check-uv
	@echo "$(BLUE)Upgrading dependencies...$(NC)"
	uv lock --upgrade
	uv sync
	@echo "$(GREEN)✓ Dependencies upgraded$(NC)"

# Backup and restore
backup-artifacts:
	@echo "$(BLUE)Backing up build artifacts...$(NC)"
	tar -czf artifacts-backup-$$(date +%Y%m%d-%H%M%S).tar.gz artifacts/ || echo "No artifacts to backup"
	@echo "$(GREEN)✓ Artifacts backed up$(NC)"