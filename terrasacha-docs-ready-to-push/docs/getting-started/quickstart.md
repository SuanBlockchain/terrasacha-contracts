# Quick Start

Get up and running with Terrasacha Contracts in minutes.

## Build Your First Contract

### 1. Compile All Contracts

Build all contracts at once:

```bash
uv run python src/scripts/build_contracts.py
```

This compiles:
- All validators in `src/terrasacha_contracts/validators/`
- All minting policies in `src/terrasacha_contracts/minting_policies/`
- Outputs to `artifacts/` directory in both `.plutus` (JSON) and `.cbor` (binary) formats

### 2. Compile Individual Contracts

Compile a specific validator:

```bash
uv run opshin compile src/terrasacha_contracts/validators/protocol.py
```

Compile a specific minting policy:

```bash
uv run opshin compile src/terrasacha_contracts/minting_policies/protocol_nfts.py
```

## Run Tests

Run all tests:

```bash
uv run pytest
```

Run specific test file:

```bash
uv run pytest tests/test_protocols.py
```

Run with coverage report:

```bash
uv run pytest --cov=src
```

Run fast tests only (exclude slow/integration):

```bash
uv run pytest -v -m "not slow"
```

## Code Quality

### Format Code

```bash
uv run ruff format .
```

### Sort Imports

```bash
uv run ruff check --select I --fix .
```

### Lint Code

```bash
uv run ruff check --fix .
```

### Type Checking

```bash
uv run mypy .
```

## Development Workflow

1. **Make changes** to contracts in `src/terrasacha_contracts/`
2. **Format and lint** your code
3. **Run tests** to ensure everything works
4. **Compile contracts** to generate artifacts
5. **Commit** your changes

### Quick Pre-Commit Check

```bash
# Format, lint, and run fast tests
uv run ruff format . && \
uv run ruff check --fix . && \
uv run pytest -v -m "not slow"
```

## Understanding Artifacts

After compilation, you'll find:

```
artifacts/
├── validators/
│   ├── protocol.plutus      # JSON format (for debugging)
│   └── protocol.cbor         # Binary format (for deployment)
└── minting_policies/
    ├── protocol_nfts.plutus
    └── protocol_nfts.cbor
```

- **`.plutus`** files: Human-readable JSON, useful for inspection
- **`.cbor`** files: Compact binary format for on-chain deployment

## Next Steps

- [Architecture Overview](../architecture/overview.md) - Understand the system design
- [Protocol Validator](../contracts/protocol-validator.md) - Deep dive into validators
- [Development Guide](development.md) - Advanced development workflows

## Common Issues

### Build Failures

If contracts fail to compile:

1. Check Python version: `python --version` (should be 3.11 or 3.12)
2. Verify OpShin installation: `uv run opshin --version`
3. Clean and rebuild: `rm -rf artifacts && uv run python src/scripts/build_contracts.py`

### Test Failures

If tests fail:

1. Ensure contracts are compiled: `uv run python src/scripts/build_contracts.py`
2. Check for missing dependencies: `uv sync --extra dev`
3. Clear cache: `rm -rf .pytest_cache .mypy_cache`
