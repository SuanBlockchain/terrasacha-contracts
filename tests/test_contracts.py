"""
Tests for OpShin contracts
"""

import pytest
from pathlib import Path
from opshin import build


# Pytest fixtures for shared test data
@pytest.fixture
def contract_paths():
    """Fixture providing contract file paths"""
    return {
        'validator': Path("src/terrasacha_contracts/validators/simple_validator.py"),
        'nft': Path("src/terrasacha_contracts/minting_policies/simple_nft.py"),
        'working_nft': Path("terrasacha_contracts/minting_policies/working_nft.py"),
        'simple_nft_fixed': Path("terrasacha_contracts/minting_policies/simple_nft_fixed.py")
    }

@pytest.fixture
def build_config():
    """Fixture providing build configuration"""
    return {
        'optimize': True,
        'min_size': 100,
        'timeout': 30
    }


class TestBuildScripts:
    """Test that build scripts work correctly"""
    
    # Class-level variables (shared across all test instances)
    contract_path_validator = Path("src/terrasacha_contracts/validators/simple_validator.py")
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


class TestUtilities:
    """Test utility functions"""
    
    def test_ada_conversion(self):
        """Test ADA to lovelace conversion"""
        from utils.helpers import ada_to_lovelace, lovelace_to_ada
        
        # Test conversion
        assert ada_to_lovelace(1.0) == 1_000_000
        assert ada_to_lovelace(5.5) == 5_500_000
        
        # Test reverse conversion
        assert lovelace_to_ada(1_000_000) == 1.0
        assert lovelace_to_ada(5_500_000) == 5.5
        
        # Test round trip
        ada_amount = 10.123456
        assert lovelace_to_ada(ada_to_lovelace(ada_amount)) == ada_amount