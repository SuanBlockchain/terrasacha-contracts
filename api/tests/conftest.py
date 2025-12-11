"""
Pytest configuration for API tests

Fixtures and configuration for FastAPI endpoint testing.
MongoDB-only architecture (PostgreSQL removed).
"""

import os
from pathlib import Path

import pytest
from dotenv import load_dotenv
from fastapi.testclient import TestClient

from api.main import app


# Load test environment variables
@pytest.fixture(scope="session", autouse=True)
def load_env():
    """Load environment variables for testing"""
    env_file = Path(__file__).parent.parent.parent / ".env"
    if env_file.exists():
        load_dotenv(env_file)

    yield


@pytest.fixture
def client():
    """Create FastAPI test client"""
    with TestClient(app) as test_client:
        yield test_client


# Auth fixtures
@pytest.fixture
def api_key():
    """Get API key from environment"""
    return os.getenv("API_KEY_DEV", "test_api_key")


@pytest.fixture
def auth_headers(api_key):
    """Get authentication headers"""
    return {"X-API-Key": api_key}


# Wallet fixtures
@pytest.fixture
def wallet_names():
    """Get available wallet names from environment"""
    wallet_keys = [k for k in os.environ.keys() if k.startswith("wallet_mnemonic")]
    if not wallet_keys:
        pytest.skip("No wallet mnemonics configured in environment")

    names = []
    for key in wallet_keys:
        if key == "wallet_mnemonic":
            names.append("default")
        else:
            # Extract role from wallet_mnemonic_<role>
            role = key.replace("wallet_mnemonic_", "")
            names.append(role)

    return names


@pytest.fixture
def default_wallet_name():
    """Get default wallet name"""
    return os.getenv("WALLET_DEFAULT_NAME", "default")


# Network fixtures
@pytest.fixture
def network():
    """Get network from environment"""
    return os.getenv("network", "testnet")


@pytest.fixture
def blockfrost_available():
    """Check if Blockfrost API key is available"""
    return bool(os.getenv("blockfrost_api_key"))
