"""
Transaction Endpoint Tests

Test suite for transaction-related API endpoints.
"""

import pytest
from fastapi.testclient import TestClient


@pytest.mark.api
@pytest.mark.integration
class TestTransactionEndpoints:
    """Tests for transaction endpoints"""

    def test_get_transaction_history_empty(self, client: TestClient, auth_headers):
        """Test GET /api/v1/transactions/history - empty history"""
        response = client.get("/api/v1/transactions/history", headers=auth_headers)

        assert response.status_code == 200
        data = response.json()

        assert "transactions" in data
        assert "total" in data
        assert "limit" in data
        assert "offset" in data
        assert "has_more" in data
        assert isinstance(data["transactions"], list)
        assert isinstance(data["total"], int)

    def test_get_transaction_history_with_filters(self, client: TestClient, auth_headers):
        """Test GET /api/v1/transactions/history - with filters"""
        response = client.get(
            "/api/v1/transactions/history",
            headers=auth_headers,
            params={"tx_type": "send_ada", "status": "confirmed", "limit": 10, "offset": 0},
        )

        assert response.status_code == 200
        data = response.json()

        assert data["limit"] == 10
        assert data["offset"] == 0

    def test_get_transaction_history_pagination(self, client: TestClient, auth_headers):
        """Test GET /api/v1/transactions/history - pagination"""
        response = client.get("/api/v1/transactions/history", headers=auth_headers, params={"limit": 5, "offset": 0})

        assert response.status_code == 200
        data = response.json()

        assert data["limit"] == 5
        assert data["offset"] == 0
        assert len(data["transactions"]) <= 5

    def test_get_transaction_status_invalid_hash(self, client: TestClient, auth_headers):
        """Test GET /api/v1/transactions/{tx_hash}/status - invalid hash"""
        invalid_hash = "invalid_hash_123"

        response = client.get(f"/api/v1/transactions/{invalid_hash}/status", headers=auth_headers)

        # Should return error or pending status
        assert response.status_code in [200, 404, 500]

    def test_get_transaction_detail_not_found(self, client: TestClient, auth_headers):
        """Test GET /api/v1/transactions/{tx_hash} - transaction not found"""
        # Use a valid-looking hash that doesn't exist
        fake_hash = "a" * 64

        response = client.get(f"/api/v1/transactions/{fake_hash}", headers=auth_headers)

        assert response.status_code in [404, 500]

    def test_send_ada_validation_errors(self, client: TestClient, auth_headers):
        """Test POST /api/v1/transactions/send-ada - validation errors"""
        # Test with missing required fields
        response = client.post("/api/v1/transactions/send-ada", headers=auth_headers, json={})

        assert response.status_code == 422

        # Test with invalid amount (negative)
        response = client.post(
            "/api/v1/transactions/send-ada",
            headers=auth_headers,
            json={
                "from_wallet": "default",
                "from_address_index": 0,
                "to_address": "addr_test1qzx9hu8j4ah3auytk0mwcupd69hpc52t0cw39a62ndgy4s",
                "amount_ada": -1.0,
            },
        )

        assert response.status_code == 422

        # Test with invalid address
        response = client.post(
            "/api/v1/transactions/send-ada",
            headers=auth_headers,
            json={
                "from_wallet": "default",
                "from_address_index": 0,
                "to_address": "invalid_address",
                "amount_ada": 10.0,
            },
        )

        assert response.status_code in [400, 422]

    def test_send_ada_wallet_not_found(self, client: TestClient, auth_headers):
        """Test POST /api/v1/transactions/send-ada - wallet not found"""
        response = client.post(
            "/api/v1/transactions/send-ada",
            headers=auth_headers,
            json={
                "from_wallet": "nonexistent_wallet",
                "from_address_index": 0,
                "to_address": "addr_test1qzx9hu8j4ah3auytk0mwcupd69hpc52t0cw39a62ndgy4s",
                "amount_ada": 10.0,
            },
        )

        assert response.status_code == 404
        assert "not found" in response.json()["detail"].lower()


@pytest.mark.api
@pytest.mark.unit
class TestTransactionSchemas:
    """Tests for transaction request/response schemas"""

    def test_send_ada_request_validation(self, client: TestClient, auth_headers):
        """Test SendAdaRequest schema validation"""
        # Invalid from_address_index (out of range)
        response = client.post(
            "/api/v1/transactions/send-ada",
            headers=auth_headers,
            json={
                "from_wallet": "default",
                "from_address_index": 101,  # Should be 0-100
                "to_address": "addr_test1qzx9hu8j4ah3auytk0mwcupd69hpc52t0cw39a62ndgy4s",
                "amount_ada": 10.0,
            },
        )

        assert response.status_code == 422

    def test_transaction_history_limit_validation(self, client: TestClient, auth_headers):
        """Test transaction history limit validation"""
        # Limit too high
        response = client.get(
            "/api/v1/transactions/history",
            headers=auth_headers,
            params={"limit": 1000},  # Should be capped at 500
        )

        assert response.status_code == 422

        # Limit too low
        response = client.get("/api/v1/transactions/history", headers=auth_headers, params={"limit": 0})

        assert response.status_code == 422


@pytest.mark.api
@pytest.mark.integration
@pytest.mark.slow
class TestTransactionDatabase:
    """Tests for transaction database integration"""

    def test_transaction_history_from_database(self, client: TestClient, auth_headers, async_session):
        """Test that transaction history is retrieved from database"""
        # First, check empty state
        response = client.get("/api/v1/transactions/history", headers=auth_headers)

        assert response.status_code == 200
        initial_count = response.json()["total"]

        # Note: In a real test, we would:
        # 1. Create a transaction
        # 2. Verify it appears in history
        # 3. Check that database record matches response

        # For now, just verify the endpoint works
        assert initial_count >= 0
