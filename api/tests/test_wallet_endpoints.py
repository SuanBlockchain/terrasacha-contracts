"""
Wallet Endpoint Tests

Comprehensive test suite for wallet-related API endpoints.
"""

import pytest
from fastapi.testclient import TestClient

from api.tests.assertions import (
    assert_error_response,
    assert_successful_response,
    assert_valid_cardano_address,
    assert_valid_wallet_response,
)
from api.tests.factories import CardanoAddressFactory, WalletFactory


@pytest.mark.api
@pytest.mark.integration
class TestWalletListEndpoint:
    """Tests for GET /api/v1/wallets/ - list all wallets"""

    def test_list_wallets_success(self, client: TestClient, auth_headers):
        """Test successful wallet listing"""
        response = client.get("/api/v1/wallets/", headers=auth_headers)
        data = assert_successful_response(response, ["wallets", "total"])

        assert isinstance(data["wallets"], list)
        assert isinstance(data["total"], int)
        assert data["total"] >= 0, "Should have zero or more wallets from database"

        # Validate first wallet structure
        if data["wallets"]:
            wallet = data["wallets"][0]
            assert "name" in wallet
            assert "network" in wallet
            assert "enterprise_address" in wallet
            assert "is_default" in wallet
            assert_valid_cardano_address(wallet["enterprise_address"], wallet["network"])

    def test_list_wallets_unauthorized(self, client: TestClient):
        """Test listing wallets without authentication"""
        response = client.get("/api/v1/wallets/")
        assert_error_response(response, 401, "API key")

    def test_list_wallets_invalid_api_key(self, client: TestClient):
        """Test listing wallets with invalid API key"""
        response = client.get("/api/v1/wallets/", headers={"X-API-Key": "invalid_key_12345"})
        assert_error_response(response, 401)  # API returns 401 for invalid key

    def test_list_wallets_response_structure(self, client: TestClient, auth_headers):
        """Test that response has consistent structure"""
        response = client.get("/api/v1/wallets/", headers=auth_headers)
        data = assert_successful_response(response)

        # Check all wallets have consistent structure
        for wallet in data["wallets"]:
            required_fields = ["name", "network", "enterprise_address", "is_default"]
            for field in required_fields:
                assert field in wallet, f"Wallet missing field: {field}"

    def test_list_wallets_identifies_default(self, client: TestClient, auth_headers):
        """Test that default wallet is correctly identified"""
        response = client.get("/api/v1/wallets/", headers=auth_headers)
        data = assert_successful_response(response)

        # Should have at most one default wallet
        default_wallets = [w for w in data["wallets"] if w["is_default"]]
        assert len(default_wallets) <= 1, f"Expected at most 1 default wallet, found {len(default_wallets)}"
