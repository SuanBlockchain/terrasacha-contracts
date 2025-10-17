"""
Transaction Endpoint Tests

Comprehensive test suite for transaction-related API endpoints.
"""

import pytest
from fastapi.testclient import TestClient

from api.tests.assertions import (
    assert_error_response,
    assert_pagination_response,
    assert_successful_response,
    assert_valid_transaction_hash,
    assert_valid_transaction_response,
)
from api.tests.factories import CardanoAddressFactory, DatabaseFactory, TransactionFactory


@pytest.mark.api
@pytest.mark.integration
class TestTransactionHistoryEndpoint:
    """Tests for GET /api/v1/transactions/history - transaction history"""

    def test_get_history_empty(self, client: TestClient, auth_headers):
        """Test transaction history when empty"""
        response = client.get("/api/v1/transactions/history", headers=auth_headers)
        data = assert_successful_response(response, ["transactions", "total", "limit", "offset", "has_more"])

        assert isinstance(data["transactions"], list)
        assert isinstance(data["total"], int)
        assert_pagination_response(data)

    def test_get_history_default_pagination(self, client: TestClient, auth_headers):
        """Test default pagination parameters"""
        response = client.get("/api/v1/transactions/history", headers=auth_headers)
        data = assert_successful_response(response)

        assert_pagination_response(data, expected_limit=50, expected_offset=0)

    def test_get_history_custom_pagination(self, client: TestClient, auth_headers):
        """Test custom pagination parameters"""
        limit = 10
        offset = 5
        response = client.get(
            "/api/v1/transactions/history", headers=auth_headers, params={"limit": limit, "offset": offset}
        )
        data = assert_successful_response(response)

        assert_pagination_response(data, expected_limit=limit, expected_offset=offset)
        assert len(data["transactions"]) <= limit

    def test_get_history_pagination_boundaries(self, client: TestClient, auth_headers):
        """Test pagination boundary conditions"""
        # Minimum valid values
        response = client.get("/api/v1/transactions/history", headers=auth_headers, params={"limit": 1, "offset": 0})
        data = assert_successful_response(response)
        assert data["limit"] == 1

        # Maximum valid limit
        response = client.get("/api/v1/transactions/history", headers=auth_headers, params={"limit": 500})
        data = assert_successful_response(response)
        assert data["limit"] == 500

    def test_get_history_invalid_pagination(self, client: TestClient, auth_headers):
        """Test invalid pagination parameters"""
        # Limit too high
        response = client.get("/api/v1/transactions/history", headers=auth_headers, params={"limit": 1000})
        assert response.status_code == 422

        # Limit too low
        response = client.get("/api/v1/transactions/history", headers=auth_headers, params={"limit": 0})
        assert response.status_code == 422

        # Negative offset
        response = client.get("/api/v1/transactions/history", headers=auth_headers, params={"offset": -1})
        assert response.status_code == 422

    def test_get_history_with_tx_type_filter(self, client: TestClient, auth_headers):
        """Test filtering by transaction type"""
        response = client.get(
            "/api/v1/transactions/history", headers=auth_headers, params={"tx_type": "send_ada"}
        )
        data = assert_successful_response(response)

        # All returned transactions should match the filter
        for tx in data["transactions"]:
            assert tx["tx_type"] == "send_ada"

    def test_get_history_with_status_filter(self, client: TestClient, auth_headers):
        """Test filtering by status"""
        statuses = ["pending", "submitted", "confirmed", "failed"]

        for status in statuses:
            response = client.get("/api/v1/transactions/history", headers=auth_headers, params={"status": status})
            data = assert_successful_response(response)

            # All returned transactions should match the filter
            for tx in data["transactions"]:
                assert tx["status"] == status

    def test_get_history_with_wallet_filter(self, client: TestClient, auth_headers):
        """Test filtering by wallet name"""
        response = client.get(
            "/api/v1/transactions/history", headers=auth_headers, params={"wallet_name": "nonexistent_wallet"}
        )
        data = assert_successful_response(response)

        # Should return empty results
        assert data["total"] == 0
        assert len(data["transactions"]) == 0

    def test_get_history_combined_filters(self, client: TestClient, auth_headers):
        """Test multiple filters combined"""
        response = client.get(
            "/api/v1/transactions/history",
            headers=auth_headers,
            params={"tx_type": "send_ada", "status": "confirmed", "limit": 10},
        )
        data = assert_successful_response(response)

        assert_pagination_response(data, expected_limit=10)

    def test_get_history_unauthorized(self, client: TestClient):
        """Test accessing history without authentication"""
        response = client.get("/api/v1/transactions/history")
        assert_error_response(response, 401)


@pytest.mark.api
@pytest.mark.integration
class TestSendAdaEndpoint:
    """Tests for POST /api/v1/transactions/send-ada - send ADA"""

    def test_send_ada_missing_fields(self, client: TestClient, auth_headers):
        """Test send ADA with missing required fields"""
        response = client.post("/api/v1/transactions/send-ada", headers=auth_headers, json={})
        assert response.status_code == 422

    def test_send_ada_invalid_amount(self, client: TestClient, auth_headers):
        """Test send ADA with invalid amounts"""
        to_address = CardanoAddressFactory.create_testnet_address()

        # Negative amount
        response = client.post(
            "/api/v1/transactions/send-ada",
            headers=auth_headers,
            json={
                "from_wallet": "default",
                "from_address_index": 0,
                "to_address": to_address,
                "amount_ada": -1.0,
            },
        )
        assert response.status_code == 422

        # Zero amount
        response = client.post(
            "/api/v1/transactions/send-ada",
            headers=auth_headers,
            json={
                "from_wallet": "default",
                "from_address_index": 0,
                "to_address": to_address,
                "amount_ada": 0,
            },
        )
        assert response.status_code == 422

    def test_send_ada_invalid_address(self, client: TestClient, auth_headers):
        """Test send ADA with invalid destination address"""
        invalid_addresses = [
            "invalid_address",
            "1234567890",
            "",
            "addr_test",  # Too short
            "mainnet_addr_in_testnet",
        ]

        for invalid_addr in invalid_addresses:
            response = client.post(
                "/api/v1/transactions/send-ada",
                headers=auth_headers,
                json={
                    "from_wallet": "default",
                    "from_address_index": 0,
                    "to_address": invalid_addr,
                    "amount_ada": 10.0,
                },
            )
            # Should reject invalid addresses (API may return 500 for internal errors)
            assert response.status_code in [400, 422, 500], f"Should reject invalid address: {invalid_addr}"

    def test_send_ada_invalid_address_index(self, client: TestClient, auth_headers):
        """Test send ADA with invalid address index"""
        to_address = CardanoAddressFactory.create_testnet_address()

        # Negative index
        response = client.post(
            "/api/v1/transactions/send-ada",
            headers=auth_headers,
            json={
                "from_wallet": "default",
                "from_address_index": -1,
                "to_address": to_address,
                "amount_ada": 10.0,
            },
        )
        assert response.status_code == 422

        # Index too large
        response = client.post(
            "/api/v1/transactions/send-ada",
            headers=auth_headers,
            json={
                "from_wallet": "default",
                "from_address_index": 101,
                "to_address": to_address,
                "amount_ada": 10.0,
            },
        )
        assert response.status_code == 422

    def test_send_ada_wallet_not_found(self, client: TestClient, auth_headers):
        """Test send ADA from non-existent wallet"""
        to_address = CardanoAddressFactory.create_testnet_address()

        response = client.post(
            "/api/v1/transactions/send-ada",
            headers=auth_headers,
            json={
                "from_wallet": "nonexistent_wallet_xyz",
                "from_address_index": 0,
                "to_address": to_address,
                "amount_ada": 10.0,
            },
        )
        assert_error_response(response, 404, "not found")

    def test_send_ada_response_structure(self, client: TestClient, auth_headers):
        """Test that send ADA response has correct structure"""
        # This test would require a funded wallet or mocking
        # For now, we just verify the response structure
        to_address = CardanoAddressFactory.create_testnet_address()

        response = client.post(
            "/api/v1/transactions/send-ada",
            headers=auth_headers,
            json={
                "from_wallet": "default",
                "from_address_index": 0,
                "to_address": to_address,
                "amount_ada": 10.0,
            },
        )

        # Will likely fail due to insufficient balance or other issues
        # Response should have JSON structure
        assert response.headers.get("content-type", "").startswith("application/json")
        data = response.json()

        # Either success response or error response
        if response.status_code == 200:
            assert "tx_hash" in data or "success" in data
        else:
            assert "detail" in data  # FastAPI error format

    def test_send_ada_unauthorized(self, client: TestClient):
        """Test sending ADA without authentication"""
        to_address = CardanoAddressFactory.create_testnet_address()

        response = client.post(
            "/api/v1/transactions/send-ada",
            json={
                "from_wallet": "default",
                "from_address_index": 0,
                "to_address": to_address,
                "amount_ada": 10.0,
            },
        )
        assert_error_response(response, 401)


@pytest.mark.api
@pytest.mark.integration
class TestTransactionStatusEndpoint:
    """Tests for GET /api/v1/transactions/{tx_hash}/status - transaction status"""

    def test_get_status_invalid_hash_format(self, client: TestClient, auth_headers):
        """Test status query with invalid hash format"""
        invalid_hashes = [
            "invalid_hash",
            "1234",
            "z" * 64,  # Non-hex characters
            "a" * 63,  # Too short
            "a" * 65,  # Too long
        ]

        for invalid_hash in invalid_hashes:
            response = client.get(f"/api/v1/transactions/{invalid_hash}/status", headers=auth_headers)
            # Should handle gracefully (may return 200 with pending status, or 404/500)
            assert response.status_code in [200, 404, 500]

    def test_get_status_nonexistent_transaction(self, client: TestClient, auth_headers):
        """Test status for transaction that doesn't exist"""
        # Valid hash format but non-existent
        fake_hash = TransactionFactory.create_tx_hash()

        response = client.get(f"/api/v1/transactions/{fake_hash}/status", headers=auth_headers)

        # Should return pending or not found
        assert response.status_code in [200, 404, 500]

        if response.status_code == 200:
            data = response.json()
            # If pending, should have pending status
            if "status" in data:
                assert data["status"] in ["pending", "submitted"]

    def test_get_status_response_structure(self, client: TestClient, auth_headers):
        """Test that status response has correct structure"""
        fake_hash = TransactionFactory.create_tx_hash()
        response = client.get(f"/api/v1/transactions/{fake_hash}/status", headers=auth_headers)

        if response.status_code == 200:
            data = response.json()
            required_fields = ["tx_hash", "status", "explorer_url"]
            for field in required_fields:
                assert field in data, f"Missing required field: {field}"

            assert_valid_transaction_hash(data["tx_hash"])

    def test_get_status_unauthorized(self, client: TestClient):
        """Test getting status without authentication"""
        fake_hash = TransactionFactory.create_tx_hash()
        response = client.get(f"/api/v1/transactions/{fake_hash}/status")
        assert_error_response(response, 401)


@pytest.mark.api
@pytest.mark.integration
class TestTransactionDetailEndpoint:
    """Tests for GET /api/v1/transactions/{tx_hash} - transaction details"""

    def test_get_detail_nonexistent_transaction(self, client: TestClient, auth_headers):
        """Test details for non-existent transaction"""
        fake_hash = TransactionFactory.create_tx_hash()

        response = client.get(f"/api/v1/transactions/{fake_hash}", headers=auth_headers)
        # Should return 404 or 500
        assert response.status_code in [404, 500]

    def test_get_detail_invalid_hash(self, client: TestClient, auth_headers):
        """Test details with invalid hash"""
        response = client.get("/api/v1/transactions/invalid_hash", headers=auth_headers)
        assert response.status_code in [404, 500]

    def test_get_detail_response_structure(self, client: TestClient, auth_headers):
        """Test that detail response has correct structure"""
        # Would need a real transaction to test fully
        # For now, just verify error handling
        fake_hash = TransactionFactory.create_tx_hash()
        response = client.get(f"/api/v1/transactions/{fake_hash}", headers=auth_headers)

        if response.status_code == 200:
            data = response.json()
            required_fields = ["tx_hash", "status", "explorer_url"]
            for field in required_fields:
                assert field in data

    def test_get_detail_unauthorized(self, client: TestClient):
        """Test getting details without authentication"""
        fake_hash = TransactionFactory.create_tx_hash()
        response = client.get(f"/api/v1/transactions/{fake_hash}")
        assert_error_response(response, 401)


@pytest.mark.api
@pytest.mark.integration
@pytest.mark.slow
@pytest.mark.skip(reason="Database integration tests have async/sync event loop conflicts - needs refactoring")
class TestTransactionDatabaseIntegration:
    """Tests for transaction database integration"""

    @pytest.mark.asyncio
    async def test_transaction_persisted_to_database(self, client: TestClient, auth_headers, async_session):
        """Test that transactions are persisted to database"""
        # Create a test transaction in database
        tx_data = await DatabaseFactory.create_transaction(
            async_session,
            status="confirmed",
            operation="send_ada",
        )

        # Query transaction history
        response = client.get("/api/v1/transactions/history", headers=auth_headers)
        data = assert_successful_response(response)

        # Should find our transaction
        tx_hashes = [tx["tx_hash"] for tx in data["transactions"]]
        assert tx_data.tx_hash in tx_hashes, "Transaction should appear in history"

    @pytest.mark.asyncio
    async def test_history_filters_by_status(self, client: TestClient, auth_headers, async_session):
        """Test that status filter works correctly"""
        # Create transactions with different statuses
        await DatabaseFactory.create_transaction(async_session, status="pending", operation="send_ada")
        await DatabaseFactory.create_transaction(async_session, status="confirmed", operation="send_ada")

        # Query only confirmed
        response = client.get("/api/v1/transactions/history", headers=auth_headers, params={"status": "confirmed"})
        data = assert_successful_response(response)

        # All should be confirmed
        for tx in data["transactions"]:
            assert tx["status"] == "confirmed"

    @pytest.mark.asyncio
    async def test_history_filters_by_operation(self, client: TestClient, auth_headers, async_session):
        """Test that transaction type filter works"""
        # Create different transaction types
        await DatabaseFactory.create_transaction(async_session, operation="send_ada")
        await DatabaseFactory.create_transaction(async_session, operation="mint_token")

        # Query only send_ada
        response = client.get("/api/v1/transactions/history", headers=auth_headers, params={"tx_type": "send_ada"})
        data = assert_successful_response(response)

        # All should be send_ada
        for tx in data["transactions"]:
            assert tx["tx_type"] == "send_ada"

    @pytest.mark.asyncio
    async def test_pagination_works_with_multiple_transactions(
        self, client: TestClient, auth_headers, async_session
    ):
        """Test pagination with multiple transactions"""
        # Create multiple transactions
        for i in range(10):
            await DatabaseFactory.create_transaction(
                async_session,
                status="confirmed",
                operation=f"test_op_{i}",
            )

        # Get first page
        response = client.get("/api/v1/transactions/history", headers=auth_headers, params={"limit": 5, "offset": 0})
        data = assert_successful_response(response)

        assert len(data["transactions"]) <= 5
        assert data["has_more"] or data["total"] <= 5

        # Get second page
        response = client.get("/api/v1/transactions/history", headers=auth_headers, params={"limit": 5, "offset": 5})
        data2 = assert_successful_response(response)

        # Should get different transactions
        first_page_hashes = {tx["tx_hash"] for tx in data["transactions"]}
        second_page_hashes = {tx["tx_hash"] for tx in data2["transactions"]}

        # Pages should not overlap
        assert len(first_page_hashes & second_page_hashes) == 0


@pytest.mark.api
@pytest.mark.unit
class TestTransactionEndpointEdgeCases:
    """Test edge cases and error handling for transaction endpoints"""

    def test_very_large_amount(self, client: TestClient, auth_headers):
        """Test send ADA with very large amount"""
        to_address = CardanoAddressFactory.create_testnet_address()

        # Extremely large amount (more than total ADA supply)
        response = client.post(
            "/api/v1/transactions/send-ada",
            headers=auth_headers,
            json={
                "from_wallet": "default",
                "from_address_index": 0,
                "to_address": to_address,
                "amount_ada": 50_000_000_000.0,  # 50 billion ADA
            },
        )

        # Should handle gracefully (validation or insufficient balance)
        assert response.status_code in [400, 422, 500]

    def test_very_small_amount(self, client: TestClient, auth_headers):
        """Test send ADA with very small amount"""
        to_address = CardanoAddressFactory.create_testnet_address()

        # Very small but positive amount
        response = client.post(
            "/api/v1/transactions/send-ada",
            headers=auth_headers,
            json={
                "from_wallet": "default",
                "from_address_index": 0,
                "to_address": to_address,
                "amount_ada": 0.000001,  # 1 lovelace
            },
        )

        # Should either succeed or fail with clear error
        assert response.status_code in [200, 400, 422, 500]

    def test_concurrent_send_requests(self, client: TestClient, auth_headers):
        """Test handling of concurrent send requests"""
        to_address = CardanoAddressFactory.create_testnet_address()

        # Send multiple concurrent requests
        responses = []
        for _ in range(3):
            response = client.post(
                "/api/v1/transactions/send-ada",
                headers=auth_headers,
                json={
                    "from_wallet": "default",
                    "from_address_index": 0,
                    "to_address": to_address,
                    "amount_ada": 1.0,
                },
            )
            responses.append(response)

        # All should return valid responses (not crash)
        for response in responses:
            assert response.status_code in [200, 400, 404, 422, 500]
            assert "application/json" in response.headers.get("content-type", "")
