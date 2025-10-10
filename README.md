# Cardano OpShin dApp

A Cardano decentralized application (dApp) built with OpShin smart contracts and uv for fast dependency management.

## Project Structure

```
cardano-opshin-dapp/
├── contracts/
│   ├── validators/           # OpShin validator contracts
│   └── minting_policies/     # OpShin minting policies
├── artifacts/
│   ├── validators/           # Compiled validator contracts
│   └── minting_policies/     # Compiled minting policies
├── scripts/                  # Build and utility scripts
├── utils/                    # Helper functions
├── tests/                    # Test files
└── pyproject.toml           # Project configuration
```

## Setup

1. **Install uv** (if not already installed):
   ```bash
   curl -LsSf https://astral.sh/uv/install.sh | sh
   ```

2. **Install dependencies**:
   ```bash
   uv sync
   ```

   Or with dev dependencies:
   ```bash
   uv sync --extra dev
   ```

3. **Activate the virtual environment**:
   ```bash
   source .venv/bin/activate
   ```

## Building Contracts

To compile all OpShin contracts:

```bash
uv run python scripts/build_contracts.py
```

Or compile individual contracts:

```bash
# Compile a validator
uv run opshin compile contracts/validators/simple_validator.py

# Compile a minting policy
uv run opshin compile contracts/minting_policies/simple_nft.py
```

## Development Commands

```bash
# Run tests
uv run pytest

# Format code
uv run ruff format .

# Sort imports
uv run ruff check --select I --fix .

# Lint and auto-fix issues
uv run ruff check --fix .

# Type checking
uv run mypy .

# Run OpShin commands
uv run opshin --help
uv run opshin compile <contract_file>
uv run opshin eval <contract_file>

# Add new dependency
uv add <package-name>

# Add dev dependency
uv add --dev <package-name>

# Update all dependencies
uv lock --upgrade
uv sync
```

## Environment Variables

Create a `.env` file for configuration:

```env
BLOCKFROST_PROJECT_ID=your_blockfrost_project_id
NETWORK=testnet  # or mainnet
WALLET_MNEMONIC=your_wallet_mnemonic_phrase
```

## Testing

Run the test suite:

```bash
# Using makefile (recommended)
make test

# Or directly with uv
uv run pytest tests/
```

Run tests with coverage:

```bash
make coverage
```

Run specific test types:

```bash
make test-fast           # Fast tests only (exclude slow/performance)
make test-unit          # Unit tests only
make test-integration   # Integration tests only
make test-contracts     # Contract compilation tests
```

## Development Workflow

### Quick Start with Makefile

The project includes a comprehensive makefile for common tasks. Run `make help` to see all available commands.

**Most useful commands:**

```bash
make help              # Show all available commands
make install-dev       # Install with dev dependencies
make format            # Format code with ruff
make lint              # Run all linting checks
make type-check        # Run mypy type checking
make test              # Run all tests
make test-fast         # Run fast tests (for quick feedback)
make coverage          # Run tests with coverage report
make build             # Compile all OpShin contracts
make clean             # Clean build artifacts and cache
```

### Pre-Commit Workflow

Before committing your changes, run:

```bash
make pre-commit
```

This will:
1. Format code with ruff
2. Run linting checks
3. Run fast tests

### Complete CI Workflow

To run the full CI pipeline locally:

```bash
make ci
```

This runs:
1. Install dependencies
2. Lint code
3. Type check
4. Run all tests
5. Generate coverage report
6. Build contracts

### Development Cycle

**Recommended workflow for feature development:**

```bash
# 1. Create a new feature branch
git checkout -b feature/your-feature-name

# 2. Install dependencies (if not already done)
make install-dev

# 3. Make your changes and test iteratively
make test-fast

# 4. Before committing, run pre-commit checks
make pre-commit

# 5. If everything passes, run the full CI
make ci

# 6. Commit your changes
git add .
git commit -m "feat: add new feature"

# 7. Push to remote
git push -u origin feature/your-feature-name
```

### Quick Aliases

For faster development, use these short aliases:

```bash
make t    # test-fast
make b    # build
make f    # format
make l    # lint
make c    # clean
make i    # install
```

### Individual Commands (without makefile)

If you prefer to run commands directly with uv:

```bash
# Code formatting
uv run ruff format .
uv run ruff check --select I --fix .

# Linting
uv run ruff check --fix .

# Type checking
uv run mypy

# Testing
uv run pytest
uv run pytest -v -m "not slow"  # Fast tests only
uv run pytest --cov=src --cov-report=html

# Building
uv run python src/scripts/build_contracts.py
```

### Troubleshooting

**Clear mypy cache** if you encounter module duplication errors:
```bash
make clean    # Cleans all caches including mypy
```

Or manually:
```bash
rm -rf .mypy_cache && uv run mypy
```

**Update dependencies** if you encounter version conflicts:
```bash
make update-deps
```

**Rebuild contracts** after making changes to validators:
```bash
make build
```

## Contributing

1. Fork the repository and clone it locally
2. Install development dependencies: `make install-dev`
3. Create a feature branch: `git checkout -b feature/your-feature`
4. Make your changes following the development workflow above
5. Run pre-commit checks: `make pre-commit`
6. Run full CI locally: `make ci`
7. Commit your changes with a descriptive message
8. Push and create a pull request

### Code Quality Standards

All contributions must pass:
- ✅ Code formatting (ruff format)
- ✅ Import sorting (ruff check --select I)
- ✅ Linting (ruff check)
- ✅ Type checking (mypy)
- ✅ All tests passing (pytest)
- ✅ Test coverage maintained or improved

Run `make ci` to verify all checks pass before submitting a PR.

## Resources

- [OpShin Documentation](https://opshin.opshin.dev/)
- [PyCardano Documentation](https://pycardano.readthedocs.io/)
- [Cardano Developer Portal](https://developers.cardano.org/)
- [Plutus Documentation](https://plutus.readthedocs.io/)