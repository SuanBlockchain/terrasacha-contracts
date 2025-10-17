"""
Wallet Endpoint Tests

Test suite for wallet-related API endpoints.
"""

import pytest
from fastapi.testclient import TestClient


@pytest.mark.api
@pytest.mark.integration
class TestWalletEndpoints:
    """Tests for wallet endpoints"""

    def test_list_wallets(self, client: TestClient, auth_headers):
        """Test GET /api/v1/wallets/ - list all wallets"""
        response = client.get("/api/v1/wallets/", headers=auth_headers)

        assert response.status_code == 200
        data = response.json()

        assert "wallets" in data
        assert "total" in data
        assert isinstance(data["wallets"], list)
        assert isinstance(data["total"], int)
        assert data["total"] > 0

        # Check wallet structure
        if data["wallets"]:
            wallet = data["wallets"][0]
            assert "name" in wallet
            assert "network" in wallet
            assert "enterprise_address" in wallet
            assert "is_default" in wallet

    def test_get_wallet_info(self, client: TestClient, auth_headers, default_wallet_name):
        """Test GET /api/v1/wallets/{name} - get wallet details"""
        response = client.get(f"/api/v1/wallets/{default_wallet_name}", headers=auth_headers)

        assert response.status_code == 200
        data = response.json()

        assert data["name"] == default_wallet_name
        assert "network" in data
        assert "main_addresses" in data
        assert "derived_addresses" in data

        # Check main addresses structure
        main_addr = data["main_addresses"]
        assert "enterprise" in main_addr
        assert "staking" in main_addr
        assert main_addr["enterprise"].startswith("addr")

    def test_get_wallet_balance(self, client: TestClient, auth_headers, default_wallet_name, blockfrost_available):
        """Test GET /api/v1/wallets/{name}/balance - get wallet balance"""
        if not blockfrost_available:
            pytest.skip("Blockfrost API key not configured")

        response = client.get(f"/api/v1/wallets/{default_wallet_name}/balance", headers=auth_headers)

        assert response.status_code == 200
        data = response.json()

        assert "address" in data
        assert "balance_lovelace" in data
        assert "balance_ada" in data
        assert "assets" in data
        assert isinstance(data["balance_lovelace"], int)
        assert isinstance(data["balance_ada"], (int, float))

    def test_get_wallet_addresses(self, client: TestClient, auth_headers, default_wallet_name):
        """Test GET /api/v1/wallets/{name}/addresses - get derived addresses"""
        response = client.get(
            f"/api/v1/wallets/{default_wallet_name}/addresses", headers=auth_headers, params={"count": 5}
        )

        assert response.status_code == 200
        data = response.json()

        assert "wallet_name" in data
        assert "addresses" in data
        assert isinstance(data["addresses"], list)
        assert len(data["addresses"]) <= 5

        # Check address structure
        if data["addresses"]:
            addr = data["addresses"][0]
            assert "index" in addr
            assert "enterprise" in addr
            assert "staking" in addr

    def test_get_nonexistent_wallet(self, client: TestClient, auth_headers):
        """Test GET /api/v1/wallets/{name} - wallet not found"""
        response = client.get("/api/v1/wallets/nonexistent_wallet_xyz", headers=auth_headers)

        assert response.status_code == 404
        assert "not found" in response.json()["detail"].lower()

    def test_unauthorized_access(self, client: TestClient):
        """Test endpoints without authentication"""
        response = client.get("/api/v1/wallets/")

        assert response.status_code == 403
        assert "API key" in response.json()["detail"]


@pytest.mark.api
@pytest.mark.unit
class TestWalletValidation:
    """Tests for wallet request validation"""

    def test_addresses_count_validation(self, client: TestClient, auth_headers, default_wallet_name):
        """Test address count parameter validation"""
        # Test with invalid count (too high)
        response = client.get(
            f"/api/v1/wallets/{default_wallet_name}/addresses",
            headers=auth_headers,
            params={"count": 1000},  # Should be limited
        )

        # Should either reject or cap at max
        assert response.status_code in [200, 422]

    def test_address_index_validation(self, client: TestClient, auth_headers, default_wallet_name):
        """Test address index parameter validation"""
        # Test with invalid index (negative)
        response = client.get(
            f"/api/v1/wallets/{default_wallet_name}/balance", headers=auth_headers, params={"address_index": -1}
        )

        assert response.status_code == 422
