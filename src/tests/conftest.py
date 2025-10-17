"""
Pytest configuration for contract tests

Fixtures and configuration for OpShin smart contract testing.
"""

import pytest
from opshin.ledger.api_v2 import *
from opshin.prelude import *


# Add any common fixtures here for contract tests
@pytest.fixture
def sample_tx_id():
    """Sample transaction ID for testing"""
    return TxId(bytes.fromhex("a" * 64))


@pytest.fixture
def sample_policy_id():
    """Sample policy ID for testing"""
    return bytes.fromhex("b" * 56)


@pytest.fixture
def sample_pkh():
    """Sample public key hash for testing"""
    return bytes.fromhex("e" * 56)


@pytest.fixture
def sample_address(sample_pkh):
    """Sample Cardano address for testing"""
    return Address(PubKeyCredential(sample_pkh), NoStakingCredential())
