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


class TenantContractConfig(Document):
    """
    Tenant-specific contract availability configuration - stored in admin MongoDB database

    Controls which contracts from the registry are available to each tenant.
    Stored in admin database for centralized management.

    If no config exists for a tenant → all contracts available (default).
    If config exists → only specified contracts/categories available based on filter rules.

    Filtering priority (highest to lowest):
    1. disabled_contracts - explicitly disabled contracts
    2. disabled_categories - explicitly disabled categories
    3. enabled_contracts - if set, only these contracts allowed
    4. enabled_categories - if set, only contracts in these categories allowed
    5. Default: all contracts enabled
    """

    tenant_id: Annotated[str, Indexed(unique=True)]  # References Tenant.tenant_id

    # Contract filtering (contract names from ContractName enum)
    enabled_contracts: list[str] = []  # If set, only these contracts available
    disabled_contracts: list[str] = []  # If set, all except these available

    # Category-based filtering (category names from ContractCategory enum)
    enabled_categories: list[str] = []  # If set, only contracts in these categories
    disabled_categories: list[str] = []  # If set, all except these categories

    # Feature flags
    allow_custom_contracts: bool = True  # Allow compilation from custom source code

    # Metadata
    notes: str | None = None
    created_at: datetime = BeanieField(default_factory=lambda: datetime.now(timezone.utc).replace(tzinfo=None))
    updated_at: datetime = BeanieField(default_factory=lambda: datetime.now(timezone.utc).replace(tzinfo=None))

    class Settings:
        name = "tenant_contract_configs"
        indexes = [
            IndexModel([("tenant_id", ASCENDING)], unique=True),
        ]


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


class UserSessionMongo(Document):
    """
    Frontend user session for wallet auto-unlock

    Stores encrypted wallet passwords for auto-unlock functionality.
    The password is encrypted with a session key generated by the frontend,
    allowing wallets to be unlocked without prompting the user for their password.

    Security model:
    - Session key is generated by frontend (never stored here)
    - Only session key hash is stored for verification
    - Password is encrypted with the session key
    - Auto-expires after configured duration
    - Revoked on password change

    Indexes:
    - TTL index on expires_at: Auto-deletes expired sessions
    - Compound indexes for efficient lookups
    """

    user_id: Annotated[str, Indexed()]  # Frontend user ID
    wallet_id: Annotated[str, Indexed()]  # Wallet payment key hash (references WalletMongo.id)

    # Encrypted password storage
    encrypted_wallet_password: str  # Fernet encrypted with session_key
    session_key_hash: str  # SHA256 hash of session_key (for verification)

    # Session metadata
    frontend_session_id: Annotated[str, Indexed()]  # Session ID from frontend
    expires_at: Annotated[datetime, Indexed(expireAfterSeconds=0)]  # TTL index - auto-delete expired sessions

    # Security tracking
    ip_address: str | None = None  # Client IP address
    user_agent: str | None = None  # Browser/client identifier

    # Timestamps
    created_at: datetime = BeanieField(default_factory=lambda: datetime.now(timezone.utc).replace(tzinfo=None))
    updated_at: datetime = BeanieField(default_factory=lambda: datetime.now(timezone.utc).replace(tzinfo=None))

    class Settings:
        name = "user_sessions"
        # Compound indexes for common query patterns
        indexes = [
            [("frontend_session_id", 1), ("wallet_id", 1)],  # Lookup by session + wallet
            [("user_id", 1), ("wallet_id", 1)],  # Lookup by user + wallet
            [("wallet_id", 1), ("expires_at", 1)],  # Find wallet sessions by expiration
            [("expires_at", 1)],  # Cleanup expired sessions
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
    witness_cbor: str | None = None  # Partial witness set CBOR for Plutus transactions (scripts + redeemers)
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

    # Native token/asset tracking
    assets_sent: list[dict] | None = None  # Original asset request for audit trail
    assets_hash: str | None = None  # Deterministic hash for duplicate detection

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


class ContractMongo(Document):
    """
    Smart Contract records - MongoDB/Beanie version (multi-tenant)

    Stores compiled Opshin smart contracts with versioning support.
    Contracts are compiled from source files and stored with their CBOR artifacts.

    Stored in tenant databases for multi-tenant isolation.
    Only CORE wallets can compile contracts.
    """

    # Primary identification
    policy_id: Annotated[str, Indexed(unique=True)]  # Script hash (unique contract ID)
    name: str  # Contract name from registry or custom name
    contract_type: str  # "spending" or "minting"

    # Compiled contract data
    cbor_hex: str  # Compiled CBOR hex string
    testnet_addr: str | None = None  # Testnet address (for spending validators)
    mainnet_addr: str | None = None  # Mainnet address (for spending validators)

    # Source tracking
    source_file: str  # File path of source contract
    source_hash: str  # SHA256 hash of source code for versioning
    compilation_params: list[str] | None = None  # Parameters used in compilation

    # Versioning
    version: int  # Auto-increment on recompile (1, 2, 3, ...)

    # Metadata
    network: str  # "testnet" or "mainnet"
    wallet_id: str  # Compiled by which CORE wallet (References WalletMongo.id)
    description: str | None = None  # Optional description

    # Registry linkage (connects compiled contracts to static registry)
    registry_contract_name: str | None = None  # ContractName value from registry (None for custom contracts)
    is_custom_contract: bool = False  # True if compiled from custom source (not in registry)
    category: str | None = None  # ContractCategory value from registry (None for custom contracts)

    # Reference script support
    storage_type: str = "local"  # "local" or "reference_script"
    reference_utxo: str | None = None  # UTXO where reference script is stored
    reference_tx_hash: str | None = None  # Transaction hash of reference script

    # Lifecycle status
    is_active: bool = True  # False after protocol burn invalidation
    invalidated_at: datetime | None = None  # When contract was marked invalid

    # Timestamps
    compiled_at: datetime  # When this version was compiled
    created_at: datetime = BeanieField(default_factory=lambda: datetime.now(timezone.utc).replace(tzinfo=None))
    updated_at: datetime = BeanieField(default_factory=lambda: datetime.now(timezone.utc).replace(tzinfo=None))

    class Settings:
        name = "contracts"  # Collection name
        indexes = [
            IndexModel([("policy_id", ASCENDING)], unique=True),
            IndexModel([("name", ASCENDING)]),
            IndexModel([("network", ASCENDING)]),
            IndexModel([("wallet_id", ASCENDING)]),
            IndexModel([("contract_type", ASCENDING)]),
            IndexModel([("name", ASCENDING), ("version", DESCENDING)]),  # Latest version lookup
            IndexModel([("category", ASCENDING)]),  # Filter by category
            IndexModel([("is_custom_contract", ASCENDING)]),  # Filter custom vs registry contracts
        ]
