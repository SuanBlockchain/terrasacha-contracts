"""
Pytest configuration for API tests

Fixtures and configuration for FastAPI endpoint testing.
"""

import os
from pathlib import Path
from typing import AsyncGenerator

import pytest
import pytest_asyncio
from dotenv import load_dotenv
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import NullPool
from sqlmodel import SQLModel

from api.database.connection import get_session
from api.main import app


# Load test environment variables
@pytest.fixture(scope="session", autouse=True)
def load_env():
    """Load environment variables for testing"""
    env_file = Path(__file__).parent.parent.parent / ".env"
    if env_file.exists():
        load_dotenv(env_file)

    # Ensure we're using test database
    if not os.getenv("POSTGRES_DB", "").endswith("_test"):
        os.environ["POSTGRES_DB"] = os.getenv("POSTGRES_DB", "terrasacha_db") + "_test"

    yield


# Database fixtures
@pytest.fixture(scope="session")
def test_database_url():
    """Get test database URL (async)"""
    from api.config import db_settings

    return db_settings.async_database_url


@pytest_asyncio.fixture
async def async_engine(test_database_url):
    """Create async engine for testing"""
    engine = create_async_engine(
        test_database_url,
        echo=False,
        poolclass=NullPool,  # Don't pool connections in tests
    )

    # Create all tables
    async with engine.begin() as conn:
        await conn.run_sync(SQLModel.metadata.create_all)

    yield engine

    # Drop all tables after tests
    async with engine.begin() as conn:
        await conn.run_sync(SQLModel.metadata.drop_all)

    await engine.dispose()


@pytest_asyncio.fixture
async def async_session(async_engine) -> AsyncGenerator[AsyncSession, None]:
    """Create async session for testing"""
    async_session_maker = sessionmaker(async_engine, class_=AsyncSession, expire_on_commit=False)

    async with async_session_maker() as session:
        yield session


@pytest.fixture
def override_get_session(async_session: AsyncSession):
    """Override get_session dependency for testing"""

    async def _override_get_session():
        yield async_session

    return _override_get_session


@pytest.fixture
def client(override_get_session):
    """Create FastAPI test client"""
    # Override database dependency
    app.dependency_overrides[get_session] = override_get_session

    with TestClient(app) as test_client:
        yield test_client

    # Clear overrides after test
    app.dependency_overrides.clear()


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
