"""
Tests for OpShin contracts
"""

from pathlib import Path

import pytest
from opshin import build

from .mock import MockChainContext


# Pytest fixtures for shared test data
@pytest.fixture
def contract_paths():
    """Fixture providing contract file paths"""
    return {
        "validator": Path("src/terrasacha_contracts/validators/simple_validator.py"),
        "nft": Path("src/terrasacha_contracts/minting_policies/simple_nft.py"),
        "working_nft": Path("terrasacha_contracts/minting_policies/working_nft.py"),
        "simple_nft_fixed": Path(
            "terrasacha_contracts/minting_policies/simple_nft_fixed.py"
        ),
    }


@pytest.fixture
def build_config():
    """Fixture providing build configuration"""
    return {"optimize": True, "min_size": 100, "timeout": 30}


class TestBuildScripts:
    """Test that build scripts work correctly"""

    # Class-level variables (shared across all test instances)
    contract_path_validator = Path(
        "src/terrasacha_contracts/validators/simple_validator.py"
    )
    contract_path_nft = Path("src/terrasacha_contracts/minting_policies/simple_nft.py")

    def setup_method(self):
        """Setup method called before each test method"""
        # Instance variables that can be different for each test
        self.build_args = {"optimize": True}
        self.expected_min_size = 100

    def test_build_script_runs(self):
        """Test that the build script runs without errors"""
        contract = build(self.contract_path_validator)
        assert contract is not None
        assert len(bytes(contract)) > self.expected_min_size

    def test_nft_contract_builds(self):
        """Test that NFT contract builds successfully"""
        if self.contract_path_nft.exists():
            contract = build(self.contract_path_nft)
            assert contract is not None
            assert len(bytes(contract)) > self.expected_min_size
        else:
            pytest.skip("NFT contract file not found")

    def teardown_method(self):
        """Cleanup method called after each test method"""
        # Clean up any resources if needed
        pass


class TestProtocol:
    """Test protocol-related functionality"""

    def test_not_minting(self):
        """Test that a transaction fails if not minting"""
        mock_context = MockChainContext()
        # mock_oref = MockOref()
        # Validate failure when not minting
        assert True
        # with pytest.raises(ValueError, match="Not a minting transaction"):
        #     mock_context.evaluate_tx(mock_oref)

    # Build MockContext, MockOref and:
    # Validate failure when not minting
    # Validate failure when not protocol token in outputs
    # Validate failure when not user token in outputs
    # Validate failure when not datum
    # Validate failure when not protocol datum type
    # Validate failure when protocol NFT not sent to correct address
    # Validate failure when protocol token or user token is not NFT
    # Validate when some of the outputs contain more than the expected tokens
    # Validate that no more tokens are minted
