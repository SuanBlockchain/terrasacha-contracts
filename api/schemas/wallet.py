"""
Wallet Schemas

Pydantic models for wallet-related API requests and responses.
"""

from datetime import datetime

from pydantic import BaseModel, Field


# ============================================================================
# Wallet Response Schemas
# ============================================================================


class WalletAddressInfo(BaseModel):
    """Wallet address information"""

    enterprise: str = Field(description="Enterprise address (payment only)")
    staking: str | None = Field(None, description="Staking address (payment + stake)")


class DerivedAddressInfo(BaseModel):
    """Derived address information"""

    index: int = Field(description="Derivation index")
    path: str = Field(description="Derivation path")
    enterprise_address: str
    staking_address: str


class WalletBalanceInfo(BaseModel):
    """Balance information for a wallet address"""

    address: str
    balance_lovelace: int = Field(description="Balance in lovelace")
    balance_ada: float = Field(description="Balance in ADA")


class WalletBalances(BaseModel):
    """Complete balance information for a wallet"""

    main_addresses: dict[str, WalletBalanceInfo] = Field(
        description="Main addresses with balances (enterprise and staking)"
    )
    derived_addresses: list[WalletBalanceInfo] = Field(
        default_factory=list, description="Derived addresses with balances"
    )
    total_balance_lovelace: int = Field(description="Total balance across all addresses in lovelace")
    total_balance_ada: float = Field(description="Total balance across all addresses in ADA")


class WalletInfoResponse(BaseModel):
    """Detailed wallet information response"""

    id: str = Field(description="Wallet ID (payment key hash)")
    name: str = Field(description="Wallet name")
    network: str = Field(description="Network (testnet/mainnet)")
    enterprise_address: str = Field(description="Enterprise address (payment only)")
    staking_address: str = Field(description="Staking address (payment + stake)")
    role: str = Field(description="Wallet role (user/core)")
    is_locked: bool = Field(description="Lock status")
    is_default: bool = Field(default=False, description="Whether this is the default/active wallet")
    created_at: datetime = Field(description="Wallet creation timestamp")


class WalletListItem(BaseModel):
    """Wallet list item for summary responses"""

    id: str = Field(description="Wallet ID (payment key hash)")
    name: str
    network: str
    enterprise_address: str
    is_default: bool = Field(default=False)
    role: str = Field(description="Wallet role (user/core)")
    is_locked: bool = Field(description="Lock status")


class WalletListResponse(BaseModel):
    """List of wallets response"""

    wallets: list[WalletListItem]
    total: int = Field(description="Total number of wallets")
    default_wallet: str | None = Field(None, description="Name of the default wallet")


# ============================================================================
# Wallet Session Management Schemas
# ============================================================================


class UnlockWalletRequest(BaseModel):
    """Request to unlock a wallet with password"""

    password: str = Field(min_length=1, description="Wallet password")

    class Config:
        json_schema_extra = {
            "example": {
                "password": "MySecureP@ssw0rd"
            }
        }


class UnlockWalletResponse(BaseModel):
    """Response after successfully unlocking a wallet"""

    success: bool = Field(default=True)
    wallet_id: str = Field(description="Wallet ID (payment key hash)")
    wallet_name: str = Field(description="Wallet name")
    wallet_role: str = Field(description="Wallet role (user/core)")
    access_token: str = Field(description="JWT access token (use in Authorization header)")
    refresh_token: str = Field(description="JWT refresh token (use to get new access tokens)")
    token_type: str = Field(default="Bearer", description="Token type")
    expires_in: int = Field(description="Access token expiration time in seconds")
    expires_at: datetime = Field(description="Access token expiration datetime")

    class Config:
        json_schema_extra = {
            "example": {
                "success": True,
                "wallet_id": "abc123def456...",
                "wallet_name": "my_wallet",
                "wallet_role": "user",
                "access_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
                "refresh_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
                "token_type": "Bearer",
                "expires_in": 1800,
                "expires_at": "2025-10-31T03:30:00Z"
            }
        }


class LockWalletResponse(BaseModel):
    """Response after locking a wallet"""

    success: bool = Field(default=True)
    wallet_id: str = Field(description="Wallet ID (payment key hash)")
    wallet_name: str = Field(description="Wallet name")
    message: str = Field(description="Success message")

    class Config:
        json_schema_extra = {
            "example": {
                "success": True,
                "wallet_id": "abc123def456...",
                "wallet_name": "my_wallet",
                "message": "Wallet locked successfully"
            }
        }


class RefreshTokenRequest(BaseModel):
    """Request to refresh an access token"""

    refresh_token: str = Field(description="Refresh token obtained from unlock")

    class Config:
        json_schema_extra = {
            "example": {
                "refresh_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9..."
            }
        }


class RefreshTokenResponse(BaseModel):
    """Response with new access token"""

    success: bool = Field(default=True)
    access_token: str = Field(description="New JWT access token")
    token_type: str = Field(default="Bearer", description="Token type")
    expires_in: int = Field(description="Access token expiration time in seconds")
    expires_at: datetime = Field(description="Access token expiration datetime")

    class Config:
        json_schema_extra = {
            "example": {
                "success": True,
                "access_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
                "token_type": "Bearer",
                "expires_in": 1800,
                "expires_at": "2025-10-31T03:30:00Z"
            }
        }


# ============================================================================
# Wallet Creation & Import Schemas
# ============================================================================


class CreateWalletRequest(BaseModel):
    """Request to create a new wallet"""

    name: str = Field(min_length=1, max_length=50, description="Unique wallet name")
    password: str = Field(min_length=8, max_length=128, description="Password for wallet encryption (min 8 characters)")
    network: str = Field(default="testnet", description="Network: 'testnet' or 'mainnet'")

    class Config:
        json_schema_extra = {
            "example": {
                "name": "my_wallet",
                "password": "MySecureP@ssw0rd",
                "network": "testnet"
            }
        }


class CreateWalletResponse(BaseModel):
    """Response for wallet creation"""

    success: bool = Field(default=True)
    wallet_id: str = Field(description="Wallet ID (payment key hash)")
    name: str = Field(description="Wallet name")
    network: str = Field(description="Network (testnet/mainnet)")
    role: str = Field(description="Wallet role (user/core)")
    enterprise_address: str = Field(description="Enterprise address (payment only)")
    staking_address: str = Field(description="Staking address (payment + stake)")
    mnemonic: str = Field(description="BIP39 mnemonic phrase - SAVE THIS SECURELY! Shown only once.")
    warning: str = Field(
        default="⚠️  IMPORTANT: Save your mnemonic phrase securely! It will not be shown again. "
        "You need it to recover your wallet if you forget your password."
    )
    created_at: datetime = Field(description="Wallet creation timestamp")

    class Config:
        json_schema_extra = {
            "example": {
                "success": True,
                "wallet_id": "a1b2c3d4e5f6...",
                "name": "my_wallet",
                "network": "testnet",
                "role": "user",
                "enterprise_address": "addr_test1vz...",
                "staking_address": "addr_test1qz...",
                "mnemonic": "word1 word2 ... word24",
                "warning": "⚠️  IMPORTANT: Save your mnemonic phrase securely!",
                "created_at": "2025-10-30T12:00:00"
            }
        }


class ImportWalletRequest(BaseModel):
    """Request to import an existing wallet"""

    name: str = Field(min_length=1, max_length=50, description="Unique wallet name")
    mnemonic: str = Field(min_length=23, description="BIP39 mnemonic phrase (12-24 words)")
    password: str = Field(min_length=8, max_length=128, description="Password for wallet encryption")
    network: str = Field(default="testnet", description="Network: 'testnet' or 'mainnet'")

    class Config:
        json_schema_extra = {
            "example": {
                "name": "imported_wallet",
                "mnemonic": "word1 word2 word3 ... word24",
                "password": "MySecureP@ssw0rd",
                "network": "testnet"
            }
        }


class ImportWalletResponse(BaseModel):
    """Response for wallet import"""

    success: bool = Field(default=True)
    wallet_id: str = Field(description="Wallet ID (payment key hash)")
    name: str = Field(description="Wallet name")
    network: str = Field(description="Network (testnet/mainnet)")
    role: str = Field(description="Wallet role (user)")
    enterprise_address: str = Field(description="Enterprise address (payment only)")
    staking_address: str = Field(description="Staking address (payment + stake)")
    imported_at: datetime = Field(description="Import timestamp")

    class Config:
        json_schema_extra = {
            "example": {
                "success": True,
                "wallet_id": "b2c3d4e5f6a7...",
                "name": "imported_wallet",
                "network": "testnet",
                "role": "user",
                "enterprise_address": "addr_test1vz...",
                "staking_address": "addr_test1qz...",
                "imported_at": "2025-10-30T12:00:00"
            }
        }


# ============================================================================
# Wallet Request Schemas
# ============================================================================


class GenerateAddressesRequest(BaseModel):
    """Request to generate new addresses for a wallet"""

    count: int = Field(default=1, ge=1, le=20, description="Number of addresses to generate (1-20)")


class GenerateAddressesResponse(BaseModel):
    """Response for generated addresses"""

    wallet_name: str
    addresses: list[DerivedAddressInfo]
    count: int = Field(description="Number of addresses generated")


class WalletBalanceRequest(BaseModel):
    """Request to check wallet balances"""

    limit_addresses: int = Field(default=5, ge=1, le=20, description="Number of derived addresses to check (1-20)")


class WalletBalanceResponse(BaseModel):
    """Response with wallet balance information"""

    wallet_name: str
    balances: WalletBalances
    checked_at: datetime = Field(default_factory=datetime.utcnow, description="When the balance was checked")


class WalletExportData(BaseModel):
    """Export data for a single wallet"""

    name: str
    network: str
    addresses: WalletAddressInfo
    derived_addresses: list[DerivedAddressInfo]
    created_at: datetime | None


class WalletExportResponse(BaseModel):
    """Response for wallet export operation"""

    export_timestamp: datetime = Field(default_factory=datetime.utcnow)
    wallets: list[WalletExportData]
    total_wallets: int


class DeleteWalletRequest(BaseModel):
    """Request to delete a wallet"""

    password: str = Field(min_length=8, description="Wallet password for confirmation")


class DeleteWalletResponse(BaseModel):
    """Response for wallet deletion"""

    success: bool = Field(default=True)
    message: str = Field(description="Success message")
    wallet_id: str = Field(description="ID of the deleted wallet")


# ============================================================================
# Error Response Schemas
# ============================================================================


class ErrorDetail(BaseModel):
    """Error detail information"""

    code: str = Field(description="Error code")
    message: str = Field(description="Human-readable error message")
    field: str | None = Field(None, description="Field that caused the error (if applicable)")


class ErrorResponse(BaseModel):
    """Standard error response"""

    success: bool = Field(default=False)
    error: str = Field(description="Error message")
    details: list[ErrorDetail] | None = Field(None, description="Additional error details")
