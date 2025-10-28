"""
Custom Assertions for API Testing

Provides reusable assertion functions for validating Cardano-specific data.
"""

import re


def assert_valid_cardano_address(address: str, network: str = "testnet"):
    """Assert that a string is a valid Cardano address format"""
    if network == "testnet":
        assert address.startswith(("addr_test1", "stake_test1")), f"Invalid testnet address: {address}"
    else:
        assert address.startswith(("addr1", "stake1")), f"Invalid mainnet address: {address}"

    # Check length (addresses are typically 58-108 characters)
    assert 50 <= len(address) <= 120, f"Invalid address length: {len(address)}"


def assert_valid_transaction_hash(tx_hash: str):
    """Assert that a string is a valid transaction hash"""
    assert len(tx_hash) == 64, f"Transaction hash must be 64 characters, got {len(tx_hash)}"
    assert re.match(r"^[0-9a-f]{64}$", tx_hash), f"Invalid transaction hash format: {tx_hash}"


def assert_valid_policy_id(policy_id: str):
    """Assert that a string is a valid policy ID"""
    assert len(policy_id) == 56, f"Policy ID must be 56 characters, got {len(policy_id)}"
    assert re.match(r"^[0-9a-f]{56}$", policy_id), f"Invalid policy ID format: {policy_id}"


def assert_successful_response(response, expected_keys: list[str] | None = None):
    """Assert that an API response is successful and contains expected keys"""
    assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"

    data = response.json()

    if expected_keys:
        for key in expected_keys:
            assert key in data, f"Missing key '{key}' in response: {data.keys()}"

    return data


def assert_error_response(response, expected_status: int, error_message_contains: str | None = None):
    """Assert that an API response is an error with expected status and message"""
    assert response.status_code == expected_status, f"Expected {expected_status}, got {response.status_code}"

    data = response.json()
    assert "detail" in data, f"Error response missing 'detail' field: {data}"

    if error_message_contains:
        detail = data["detail"].lower()
        assert error_message_contains.lower() in detail, (
            f"Expected '{error_message_contains}' in error message, got: {data['detail']}"
        )

    return data


def assert_valid_balance_response(data: dict):
    """Assert that a balance response has valid structure"""
    required_keys = ["address", "balance_lovelace", "balance_ada", "assets"]
    for key in required_keys:
        assert key in data, f"Missing key '{key}' in balance response"

    assert isinstance(data["balance_lovelace"], int), "balance_lovelace must be integer"
    assert isinstance(data["balance_ada"], (int, float)), "balance_ada must be numeric"
    assert isinstance(data["assets"], list), "assets must be a list"
    assert data["balance_lovelace"] >= 0, "Balance cannot be negative"


def assert_valid_transaction_response(data: dict):
    """Assert that a transaction response has valid structure"""
    required_keys = ["tx_hash", "status"]
    for key in required_keys:
        assert key in data, f"Missing key '{key}' in transaction response"

    assert_valid_transaction_hash(data["tx_hash"])

    valid_statuses = ["pending", "submitted", "confirmed", "failed"]
    assert data["status"] in valid_statuses, f"Invalid status: {data['status']}"


def assert_valid_wallet_response(data: dict):
    """Assert that a wallet response has valid structure"""
    required_keys = ["name", "network", "main_addresses"]
    for key in required_keys:
        assert key in data, f"Missing key '{key}' in wallet response"

    # Check main addresses structure
    main_addr = data["main_addresses"]
    assert "enterprise" in main_addr, "Missing enterprise address"
    assert "staking" in main_addr, "Missing staking address"

    # Validate address formats
    assert_valid_cardano_address(main_addr["enterprise"], data["network"])
    assert_valid_cardano_address(main_addr["staking"], data["network"])


def assert_pagination_response(data: dict, expected_limit: int | None = None, expected_offset: int | None = None):
    """Assert that a paginated response has valid structure"""
    required_keys = ["total", "limit", "offset", "has_more"]
    for key in required_keys:
        assert key in data, f"Missing key '{key}' in pagination response"

    assert isinstance(data["total"], int), "total must be integer"
    assert isinstance(data["limit"], int), "limit must be integer"
    assert isinstance(data["offset"], int), "offset must be integer"
    assert isinstance(data["has_more"], bool), "has_more must be boolean"

    if expected_limit is not None:
        assert data["limit"] == expected_limit, f"Expected limit {expected_limit}, got {data['limit']}"

    if expected_offset is not None:
        assert data["offset"] == expected_offset, f"Expected offset {expected_offset}, got {data['offset']}"

    # Validate has_more logic
    if data["offset"] + data["limit"] >= data["total"]:
        assert not data["has_more"], "has_more should be False when no more results available"
