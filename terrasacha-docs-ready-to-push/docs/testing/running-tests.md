# Running Tests

How to run tests in Terrasacha Contracts.

## Basic Usage

Run all tests:
```bash
uv run pytest
```

Run with verbose output:
```bash
uv run pytest -v
```

Run specific test file:
```bash
uv run pytest tests/test_protocols.py
```

Run specific test function:
```bash
uv run pytest tests/test_protocols.py::test_protocol_update
```

## Test Selection

### By Marker

Run only unit tests:
```bash
uv run pytest -m unit
```

Run only integration tests:
```bash
uv run pytest -m integration
```

Exclude slow tests:
```bash
uv run pytest -m "not slow"
```

Multiple markers:
```bash
uv run pytest -m "unit or integration"
```

### By Keyword

Run tests matching keyword:
```bash
uv run pytest -k "protocol"
```

Exclude tests with keyword:
```bash
uv run pytest -k "not burn"
```

## Coverage Reports

Run with coverage:
```bash
uv run pytest --cov=src
```

Generate HTML coverage report:
```bash
uv run pytest --cov=src --cov-report=html
```

View report:
```bash
open htmlcov/index.html  # macOS
xdg-open htmlcov/index.html  # Linux
```

Generate XML coverage (for CI):
```bash
uv run pytest --cov=src --cov-report=xml
```

## Parallel Execution

Run tests in parallel (faster):
```bash
uv run pytest -n auto
```

Specify number of workers:
```bash
uv run pytest -n 4
```

## Output Control

Stop on first failure:
```bash
uv run pytest -x
```

Show local variables on failure:
```bash
uv run pytest -l
```

Capture output (show print statements):
```bash
uv run pytest -s
```

## Test Discovery

List all tests without running:
```bash
uv run pytest --collect-only
```

Show test names and markers:
```bash
uv run pytest --markers
```

## Performance Testing

Run performance benchmarks:
```bash
uv run pytest -m performance --benchmark-only
```

Save benchmark results:
```bash
uv run pytest --benchmark-save=baseline
```

Compare benchmarks:
```bash
uv run pytest --benchmark-compare=baseline
```

## Watch Mode

Auto-run tests on file changes:
```bash
uv run pytest-watch
```

## Common Workflows

### Quick Feedback Loop

For rapid development:
```bash
uv run pytest -m "not slow" -x
```

### Pre-Commit Check

Before committing:
```bash
uv run pytest --cov=src --cov-report=term-missing
```

### Full CI Run

Complete test suite:
```bash
uv run pytest --cov=src --cov-report=html --cov-report=xml -n auto
```

## Troubleshooting

### Clear Cache

If tests behave unexpectedly:
```bash
rm -rf .pytest_cache
uv run pytest --cache-clear
```

### Rebuild Contracts

If contract tests fail:
```bash
uv run python src/scripts/build_contracts.py
uv run pytest -m contracts
```

### Verbose Debug

Show maximum detail:
```bash
uv run pytest -vv -s -l
```

## See Also

- [Testing Overview](overview.md)
- [Development Guide](../getting-started/development.md)
