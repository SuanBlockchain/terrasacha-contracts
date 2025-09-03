---
description: "Run comprehensive tests for OpShin validators and contracts"
tools: ["bash"]
---

# Test Validators

Run the complete test suite for OpShin validators and smart contracts with optional filtering.

Usage:
- `/test-validators` - Run all tests
- `/test-validators protocol` - Run tests matching "protocol"
- `/test-validators --slow` - Include slow/integration tests

This will:
1. Execute pytest with coverage reporting
2. Test all validators and minting policies
3. Validate contract logic and edge cases
4. Generate coverage reports in `htmlcov/`

```bash
poetry run pytest tests/ --cov=src --cov-report=term-missing --cov-report=html ${ARGUMENTS:+-k "$ARGUMENTS"}
```

Common test categories:
- `unit` - Fast unit tests
- `integration` - Integration tests with Cardano
- `contracts` - Contract compilation/validation tests
- `performance` - Performance benchmarking tests

Use `-m "not slow"` to skip time-consuming tests during development.