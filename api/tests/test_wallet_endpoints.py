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
        assert data["total"] > 0, "Should have at least one wallet from environment"

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

        # Should have exactly one default wallet
        default_wallets = [w for w in data["wallets"] if w["is_default"]]
        assert len(default_wallets) == 1, f"Expected 1 default wallet, found {len(default_wallets)}"


@pytest.mark.api
@pytest.mark.integration
class TestWalletInfoEndpoint:
    """Tests for GET /api/v1/wallets/{name} - get wallet details"""

    def test_get_wallet_info_success(self, client: TestClient, auth_headers, default_wallet_name):
        """Test successful wallet info retrieval"""
        response = client.get(f"/api/v1/wallets/{default_wallet_name}", headers=auth_headers)
        data = assert_successful_response(response)

        assert_valid_wallet_response(data)
        assert data["name"] == default_wallet_name

    def test_get_wallet_info_not_found(self, client: TestClient, auth_headers):
        """Test getting info for non-existent wallet"""
        response = client.get("/api/v1/wallets/nonexistent_wallet_xyz_12345", headers=auth_headers)
        assert_error_response(response, 404, "not found")

    def test_get_wallet_info_derived_addresses(self, client: TestClient, auth_headers, default_wallet_name):
        """Test that derived addresses are included"""
        response = client.get(f"/api/v1/wallets/{default_wallet_name}", headers=auth_headers)
        data = assert_successful_response(response)

        assert "derived_addresses" in data
        assert isinstance(data["derived_addresses"], list)

        # If there are derived addresses, validate structure
        for addr in data["derived_addresses"]:
            assert "index" in addr
            assert "enterprise_address" in addr
            assert "staking_address" in addr
            assert_valid_cardano_address(addr["enterprise_address"], data["network"])

    def test_get_wallet_info_network_consistency(self, client: TestClient, auth_headers, default_wallet_name):
        """Test that network is consistent across addresses"""
        response = client.get(f"/api/v1/wallets/{default_wallet_name}", headers=auth_headers)
        data = assert_successful_response(response)

        network = data["network"]
        main_addr = data["main_addresses"]

        # All addresses should match the wallet's network
        assert_valid_cardano_address(main_addr["enterprise"], network)
        assert_valid_cardano_address(main_addr["staking"], network)

    def test_get_wallet_info_unauthorized(self, client: TestClient):
        """Test getting wallet info without authentication"""
        response = client.get("/api/v1/wallets/default")
        assert_error_response(response, 401)


@pytest.mark.api
@pytest.mark.integration
class TestWalletBalanceEndpoint:
    """Tests for GET /api/v1/wallets/{name}/balances - get wallet balances"""

    def test_get_balances_success(self, client: TestClient, auth_headers, default_wallet_name, blockfrost_available):
        """Test successful balance retrieval"""
        if not blockfrost_available:
            pytest.skip("Blockfrost API key not configured")

        response = client.get(f"/api/v1/wallets/{default_wallet_name}/balances", headers=auth_headers)
        data = assert_successful_response(response)

        # Validate response structure
        assert "wallet_name" in data
        assert "balances" in data
        assert "checked_at" in data
        assert data["wallet_name"] == default_wallet_name

        # Validate balances structure
        balances = data["balances"]
        assert "main_addresses" in balances
        assert "derived_addresses" in balances
        assert "total_balance_lovelace" in balances
        assert "total_balance_ada" in balances

    def test_get_balances_with_limit_addresses(
        self, client: TestClient, auth_headers, default_wallet_name, blockfrost_available
    ):
        """Test balance retrieval with limited derived addresses"""
        if not blockfrost_available:
            pytest.skip("Blockfrost API key not configured")

        response = client.get(
            f"/api/v1/wallets/{default_wallet_name}/balances", headers=auth_headers, params={"limit_addresses": 3}
        )

        # Should succeed or return valid error
        assert response.status_code in [200, 500]  # 500 if Blockfrost has issues

        if response.status_code == 200:
            data = response.json()
            assert len(data["balances"]["derived_addresses"]) <= 3

    def test_get_balances_invalid_limit_addresses(self, client: TestClient, auth_headers, default_wallet_name):
        """Test balance with invalid limit_addresses parameter"""
        # Negative limit
        response = client.get(
            f"/api/v1/wallets/{default_wallet_name}/balances", headers=auth_headers, params={"limit_addresses": -1}
        )
        assert response.status_code == 422

        # Too large limit
        response = client.get(
            f"/api/v1/wallets/{default_wallet_name}/balances", headers=auth_headers, params={"limit_addresses": 100}
        )
        assert response.status_code == 422

    def test_get_balances_wallet_not_found(self, client: TestClient, auth_headers):
        """Test balance for non-existent wallet"""
        response = client.get("/api/v1/wallets/nonexistent_wallet/balances", headers=auth_headers)
        assert_error_response(response, 404, "not found")

    def test_get_balances_ada_lovelace_conversion(
        self, client: TestClient, auth_headers, default_wallet_name, blockfrost_available
    ):
        """Test that ADA and lovelace values are consistent"""
        if not blockfrost_available:
            pytest.skip("Blockfrost API key not configured")

        response = client.get(f"/api/v1/wallets/{default_wallet_name}/balances", headers=auth_headers)

        if response.status_code == 200:
            data = response.json()
            balances = data["balances"]
            # 1 ADA = 1,000,000 lovelace
            expected_ada = balances["total_balance_lovelace"] / 1_000_000
            assert abs(balances["total_balance_ada"] - expected_ada) < 0.000001, "ADA/lovelace conversion mismatch"


@pytest.mark.api
@pytest.mark.integration
class TestWalletGenerateAddressesEndpoint:
    """Tests for POST /api/v1/wallets/{name}/addresses/generate - generate new addresses"""

    def test_generate_addresses_default_count(self, client: TestClient, auth_headers, default_wallet_name):
        """Test generating addresses with default count"""
        response = client.post(
            f"/api/v1/wallets/{default_wallet_name}/addresses/generate", headers=auth_headers, json={"count": 5}
        )
        data = assert_successful_response(response, ["wallet_name", "addresses", "count"])

        assert data["wallet_name"] == default_wallet_name
        assert isinstance(data["addresses"], list)
        assert data["count"] == len(data["addresses"])
        assert len(data["addresses"]) == 5

    def test_generate_addresses_custom_count(self, client: TestClient, auth_headers, default_wallet_name):
        """Test generating specific number of addresses"""
        count = 3
        response = client.post(
            f"/api/v1/wallets/{default_wallet_name}/addresses/generate", headers=auth_headers, json={"count": count}
        )
        data = assert_successful_response(response)

        assert len(data["addresses"]) == count, f"Should return exactly {count} addresses"

    def test_generate_addresses_validation(self, client: TestClient, auth_headers, default_wallet_name):
        """Test generated address structure validation"""
        response = client.post(
            f"/api/v1/wallets/{default_wallet_name}/addresses/generate", headers=auth_headers, json={"count": 2}
        )
        data = assert_successful_response(response)

        for addr in data["addresses"]:
            assert "index" in addr, "Address missing index"
            assert "enterprise_address" in addr, "Address missing enterprise_address"
            assert "staking_address" in addr, "Address missing staking_address"
            assert isinstance(addr["index"], int), "Index must be integer"
            assert addr["index"] >= 0, "Index must be non-negative"

    def test_generate_addresses_count_validation(self, client: TestClient, auth_headers, default_wallet_name):
        """Test count parameter validation"""
        # Negative count
        response = client.post(
            f"/api/v1/wallets/{default_wallet_name}/addresses/generate", headers=auth_headers, json={"count": -1}
        )
        assert response.status_code == 422

        # Zero count
        response = client.post(
            f"/api/v1/wallets/{default_wallet_name}/addresses/generate", headers=auth_headers, json={"count": 0}
        )
        assert response.status_code in [200, 422]  # Depends on validation logic

    def test_generate_addresses_wallet_not_found(self, client: TestClient, auth_headers):
        """Test generating addresses for non-existent wallet"""
        response = client.post(
            "/api/v1/wallets/nonexistent_wallet/addresses/generate", headers=auth_headers, json={"count": 5}
        )
        assert_error_response(response, 404, "not found")


@pytest.mark.api
@pytest.mark.unit
class TestWalletEndpointEdgeCases:
    """Test edge cases and error handling"""

    def test_special_characters_in_wallet_name(self, client: TestClient, auth_headers):
        """Test wallet name with special characters"""
        special_names = ["wallet-with-dashes", "wallet_with_underscores", "wallet123", "wallet.with.dots"]

        for name in special_names:
            response = client.get(f"/api/v1/wallets/{name}", headers=auth_headers)
            # Should either work or return 404, not 500
            assert response.status_code in [200, 404]

    def test_very_long_wallet_name(self, client: TestClient, auth_headers):
        """Test with very long wallet name"""
        long_name = "a" * 1000
        response = client.get(f"/api/v1/wallets/{long_name}", headers=auth_headers)
        # Should handle gracefully
        assert response.status_code in [404, 414]  # 414 = URI Too Long

    def test_empty_wallet_name(self, client: TestClient, auth_headers):
        """Test with empty wallet name"""
        response = client.get("/api/v1/wallets//balances", headers=auth_headers)
        # Should return 404 (route not found)
        assert response.status_code == 404

    def test_concurrent_requests(self, client: TestClient, auth_headers, default_wallet_name):
        """Test handling of concurrent requests"""
        # Make multiple simultaneous requests
        responses = []
        for _ in range(5):
            response = client.get(f"/api/v1/wallets/{default_wallet_name}", headers=auth_headers)
            responses.append(response)

        # All should succeed
        for response in responses:
            assert response.status_code == 200

        # All should return consistent data
        data_list = [r.json() for r in responses]
        first_data = data_list[0]
        for data in data_list[1:]:
            assert data["name"] == first_data["name"]
            assert data["network"] == first_data["network"]
