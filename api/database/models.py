"""
Database Models for Terrasacha Contracts

MongoDB/Beanie Document models for multi-tenant architecture.
All models use MongoDB with Beanie ODM (Object Document Mapper).
"""

from datetime import datetime, timezone
from typing import Annotated

from beanie import Document, Indexed
from pydantic import Field as BeanieField
from pymongo import ASCENDING, DESCENDING, IndexModel


# ============================================================================
# Multi-Tenant Models (MongoDB/Beanie - Admin Database)
# ============================================================================


class Tenant(Document):
    """
    Tenant registry - stored in admin MongoDB database

    Manages multi-tenant configuration with database-per-tenant architecture.
    Each tenant has their own isolated MongoDB database.
    """

    tenant_id: Annotated[str, Indexed(unique=True)]  # e.g., "acme_corp"
    tenant_name: str  
    database_name: str 

    # Status
    is_active: bool = True
    is_suspended: bool = False

    # Subscription
    plan_tier: str = "free"
    max_wallets: int = 10
    max_projects: int = 50

    # Metadata
    admin_email: str
    created_at: datetime = BeanieField(default_factory=lambda: datetime.now(timezone.utc).replace(tzinfo=None))
    updated_at: datetime = BeanieField(default_factory=lambda: datetime.now(timezone.utc).replace(tzinfo=None))

    class Settings:
        name = "tenants"


class ApiKey(Document):
    """
    API Key to Tenant mapping - stored in admin MongoDB database

    Maps API keys to tenants for automatic tenant identification.
    API keys are hashed using SHA256 for security.
    """

    # API Key (hashed for security)
    api_key_hash: Annotated[str, Indexed(unique=True)]  # SHA256 hash of API key
    api_key_prefix: str  # First 8 chars for identification

    # Tenant association
    tenant_id: Annotated[str, Indexed()]  # References Tenant.tenant_id

    # Key metadata
    name: str  # Descriptive name (e.g., "Production Key", "Test Key")
    is_active: bool = True

    # Permissions (future expansion)
    scopes: list[str] = BeanieField(default_factory=lambda: ["read", "write"])

    # Tracking
    created_at: datetime = BeanieField(default_factory=lambda: datetime.now(timezone.utc).replace(tzinfo=None))
    last_used_at: datetime | None = None
    expires_at: datetime | None = None  # Optional expiration
    revoked_at: datetime | None = None  # Timestamp when key was revoked

    class Settings:
        name = "api_keys"


# ============================================================================
# Tenant-Specific Models (MongoDB/Beanie - Tenant Databases)
# ============================================================================


class WalletMongo(Document):
    """
    Wallet management - MongoDB/Beanie version

    Stores wallet information with encrypted mnemonics and role-based organization.
    Supports password-based encryption for security.
    """

    id: str  # Payment key hash (PKH) - will be MongoDB _id, unique by default
    name: Annotated[str, Indexed(unique=True)]  # Unique wallet name
    network: str  # NetworkType as string

    # Encryption and security
    mnemonic_encrypted: str  # Encrypted BIP39 mnemonic (Fernet encrypted)
    encryption_salt: str  # Salt for key derivation (base64 encoded)
    password_hash: str  # Argon2 password hash

    # Wallet addresses and keys
    enterprise_address: Annotated[str, Indexed()]
    staking_address: Annotated[str, Indexed()]

    # Wallet role and status
    wallet_role: str = "user"  # WalletRole as string
    is_locked: bool = True  # Locked by default
    is_default: bool = False

    # Session tracking
    last_unlocked_at: datetime | None = None

    # Timestamps
    created_at: datetime = BeanieField(default_factory=lambda: datetime.now(timezone.utc).replace(tzinfo=None))
    updated_at: datetime = BeanieField(default_factory=lambda: datetime.now(timezone.utc).replace(tzinfo=None))

    class Settings:
        name = "wallets"


class WalletSessionMongo(Document):
    """
    Wallet session management - MongoDB/Beanie version

    Tracks active wallet sessions for token-based authentication.
    Used for session revocation and security auditing.

    Indexes:
    - TTL index on expires_at: Auto-deletes expired sessions (60s delay)
    - Compound indexes optimize common query patterns
    """

    wallet_id: Annotated[str, Indexed()]  # References WalletMongo.id

    # JWT token identification
    jti: Annotated[str, Indexed(unique=True)]  # JWT ID (jti claim) for access token
    refresh_jti: Annotated[str, Indexed(unique=True)]  # JWT ID for refresh token

    # Session metadata with indexes for performance
    expires_at: Annotated[datetime, Indexed(expireAfterSeconds=0)]  # TTL index - auto-delete expired sessions
    refresh_expires_at: datetime  # Refresh token expiration
    revoked: Annotated[bool, Indexed()] = False  # Session revoked flag (indexed for filtering)
    revoked_at: Annotated[datetime | None, Indexed()] = None  # When session was revoked (indexed for purging)
    last_used_at: datetime | None = None  # Last time session was used

    # Session tracking
    ip_address: str | None = None
    user_agent: str | None = None
    client_fingerprint: str | None = None  # Browser/device fingerprint for tracking
    session_name: str | None = None  # Human-readable session identifier (e.g., "Chrome on Mac")

    # Timestamps
    created_at: Annotated[datetime, Indexed()] = BeanieField(
        default_factory=lambda: datetime.now(timezone.utc).replace(tzinfo=None)
    )
    updated_at: datetime = BeanieField(default_factory=lambda: datetime.now(timezone.utc).replace(tzinfo=None))

    class Settings:
        name = "wallet_sessions"
        # Compound indexes for common query patterns
        indexes = [
            [("wallet_id", 1), ("revoked", 1)],  # Get wallet's active sessions
            [("expires_at", 1), ("revoked", 1)],  # Find expired non-revoked sessions (cleanup)
            [("revoked", 1), ("revoked_at", 1)],  # Find old revoked sessions (purge)
            [("revoked", 1), ("created_at", -1)],  # List active sessions sorted by date
        ]


class TransactionMongo(Document):
    """
    Transaction records - MongoDB/Beanie version (multi-tenant)

    Tracks blockchain transactions through their lifecycle:
    BUILT → SIGNED → SUBMITTED → CONFIRMED/FAILED

    Supports two-stage signing (build unsigned, then sign with password).
    """

    # Primary identification
    tx_hash: Annotated[str, Indexed(unique=True)]  # 64-char hex transaction hash
    wallet_id: str  # References WalletMongo.id (payment key hash)
    contract_policy_id: str | None = None  # References ContractMongo (future)

    # Status tracking
    status: str  # BUILT, SIGNED, PENDING, SUBMITTED, CONFIRMED, FAILED
    operation: str  # "send_ada", "mint_protocol", etc.
    description: str | None = None

    # Two-stage transaction support
    unsigned_cbor: str | None = None  # Unsigned CBOR after BUILD
    signed_cbor: str | None = None  # Signed CBOR after SIGN
    from_address_index: int | None = None  # Derivation index (0 = main)
    from_address: str | None = None
    to_address: str | None = None
    amount_lovelace: int | None = None
    estimated_fee: int | None = None

    # Amount tracking
    fee_lovelace: int | None = None
    total_output_lovelace: int | None = None

    # Complex data as native MongoDB objects
    inputs: list[dict] = []
    outputs: list[dict] = []
    tx_metadata: dict = {}

    # Confirmation tracking
    submitted_at: datetime | None = None
    confirmed_at: datetime | None = None
    block_height: int | None = None

    # Error tracking
    error_message: str | None = None

    # Timestamps
    created_at: datetime = BeanieField(default_factory=lambda: datetime.now(timezone.utc).replace(tzinfo=None))
    updated_at: datetime = BeanieField(default_factory=lambda: datetime.now(timezone.utc).replace(tzinfo=None))

    class Settings:
        name = "transactions"  # Collection name
        indexes = [
            IndexModel([("tx_hash", ASCENDING)], unique=True),
            IndexModel([("wallet_id", ASCENDING), ("created_at", DESCENDING)]),
            IndexModel([("status", ASCENDING)]),
            IndexModel([("created_at", DESCENDING)]),
        ]
