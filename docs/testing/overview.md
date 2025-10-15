# Testing Overview

Comprehensive testing strategy for Terrasacha Contracts.

## Testing Philosophy

Multi-layered testing approach:

1. **Unit Tests**: Test individual functions in isolation
2. **Integration Tests**: Test component interactions
3. **Contract Tests**: Test compiled smart contracts
4. **Property Tests**: Hypothesis-based testing for edge cases

## Test Markers

Tests are organized using pytest markers:

```python
@pytest.mark.unit
def test_datum_validation():
    """Fast unit test for datum validation logic"""
    pass

@pytest.mark.integration
def test_mint_and_update_flow():
    """Test integration between minting and validator"""
    pass

@pytest.mark.slow
def test_full_protocol_lifecycle():
    """Comprehensive test of entire protocol"""
    pass

@pytest.mark.contracts
def test_contract_compilation():
    """Verify contracts compile correctly"""
    pass

@pytest.mark.performance
def test_validator_performance():
    """Benchmark validator execution time"""
    pass
```

## Running Tests

See: [Running Tests](running-tests.md)

## Coming Soon

Detailed documentation for:
- Writing effective tests
- Mock utilities
- Test fixtures
- Coverage requirements
- Performance benchmarking

For now, see:
- [Source Code](https://github.com/SuanBlockchain/terrasacha-contracts/tree/main/tests)
