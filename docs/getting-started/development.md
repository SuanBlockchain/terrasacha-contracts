# Development Guide

Learn the recommended development workflow for Terrasacha Contracts.

## Development Cycle

### 1. Feature Development

```bash
# Create a new feature branch
git checkout -b feature/your-feature-name

# Install dependencies (if not already done)
uv sync --extra dev

# Make your changes and test iteratively
uv run pytest -v -m "not slow"  # Fast feedback loop
```

### 2. Code Quality Checks

Before committing, ensure code quality:

```bash
# Format code
uv run ruff format .

# Sort imports
uv run ruff check --select I --fix .

# Lint and fix issues
uv run ruff check --fix .

# Type checking
uv run mypy .
```

### 3. Testing

Run comprehensive tests:

```bash
# All tests
uv run pytest

# With coverage report
uv run pytest --cov=src --cov-report=html

# Specific test markers
uv run pytest -m unit          # Unit tests only
uv run pytest -m integration   # Integration tests only
uv run pytest -m contracts     # Contract tests only
uv run pytest -m "not slow"    # Fast tests only
```

### 4. Building Contracts

```bash
# Build all contracts
uv run python src/scripts/build_contracts.py

# Or use the interactive CLI menu
uv run python src/scripts/cli_menu.py
# Then select:
# - Option 2: Compile/Recompile All Contracts
# - Option 3: Compile New Project Contract Only (faster)
```

## Project Commands

### Dependency Management

```bash
# Add new dependency
uv add <package-name>

# Add dev dependency
uv add --dev <package-name>

# Update all dependencies
uv lock --upgrade
uv sync

# Show outdated packages
uv pip list --outdated
```

### OpShin Commands

```bash
# Compile a contract
uv run opshin compile <contract_file>

# Evaluate a contract (useful for testing)
uv run opshin eval <contract_file>

# Get OpShin help
uv run opshin --help
```

## Code Standards

### Formatting

The project uses **ruff** for formatting with these settings:

- Line length: 120 characters
- Quote style: double quotes
- Target version: Python 3.11

### Import Organization

Imports are organized into sections:

1. Future imports
2. Standard library
3. Third-party packages
4. First-party (terrasacha_contracts)
5. Local folder imports

### Type Checking

All code must pass mypy type checking:

- Strict mode enabled
- No untyped definitions allowed
- OpShin contracts excluded from type checking

## Testing Guidelines

### Test Markers

Use pytest markers to organize tests:

```python
@pytest.mark.unit
def test_validator_logic():
    pass

@pytest.mark.integration
def test_contract_interaction():
    pass

@pytest.mark.slow
def test_full_workflow():
    pass

@pytest.mark.contracts
def test_contract_compilation():
    pass
```

### Test Structure

```python
def test_function_name():
    # Arrange - Set up test data
    datum = DatumProtocol(...)

    # Act - Execute the function
    result = validator(datum, redeemer, context)

    # Assert - Verify the result
    assert result is True
```

### Coverage Goals

- Maintain or improve test coverage
- Aim for >80% coverage on critical paths
- All new features must include tests

## Git Workflow

### Commit Messages

Follow conventional commits:

```
feat: add new minting policy for carbon credits
fix: resolve validation issue in protocol validator
docs: update architecture documentation
test: add integration tests for NFT minting
refactor: simplify UTXO resolution logic
```

### Pre-Commit Checklist

Before committing:

- [ ] Code is formatted (`uv run ruff format .`)
- [ ] Imports are sorted (`uv run ruff check --select I --fix .`)
- [ ] No lint errors (`uv run ruff check --fix .`)
- [ ] Type checking passes (`uv run mypy .`)
- [ ] Tests pass (`uv run pytest`)
- [ ] Contracts compile (`uv run python src/scripts/build_contracts.py`)

### Pull Request Process

1. Create feature branch from `main`
2. Make changes with good commit messages
3. Ensure all checks pass locally
4. Push branch and create pull request
5. Address review comments
6. Squash and merge when approved

## Troubleshooting

### Clear Caches

If you encounter issues:

```bash
# Clear Python cache
find . -type d -name __pycache__ -exec rm -rf {} +

# Clear pytest cache
rm -rf .pytest_cache

# Clear mypy cache
rm -rf .mypy_cache

# Clear build artifacts
rm -rf artifacts/
```

### Dependency Issues

```bash
# Reset virtual environment
rm -rf .venv
uv sync --extra dev
```

### Contract Compilation Errors

Check OpShin version compatibility:

```bash
uv run opshin --version  # Should be 0.26.x or compatible
```

## IDE Configuration

### VS Code

Recommended extensions:

- Python
- Pylance
- Ruff
- Even Better TOML

Settings (`.vscode/settings.json`):

```json
{
  "python.defaultInterpreterPath": ".venv/bin/python",
  "python.linting.enabled": true,
  "python.linting.ruffEnabled": true,
  "python.formatting.provider": "none",
  "[python]": {
    "editor.defaultFormatter": "charliermarsh.ruff",
    "editor.formatOnSave": true,
    "editor.codeActionsOnSave": {
      "source.organizeImports": true
    }
  }
}
```

## Next Steps

- [Architecture Overview](../architecture/overview.md)
- [API Reference](../api/validators.md)
- [Testing Guide](../testing/overview.md)
