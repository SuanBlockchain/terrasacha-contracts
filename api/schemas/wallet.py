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

    name: str = Field(description="Wallet name/role")
    network: str = Field(description="Network (testnet/mainnet)")
    main_addresses: WalletAddressInfo = Field(description="Main addresses")
    derived_addresses: list[DerivedAddressInfo] = Field(default_factory=list, description="Derived addresses")
    is_default: bool = Field(default=False, description="Whether this is the default/active wallet")
    created_at: datetime | None = Field(None, description="Wallet creation timestamp")


class WalletListItem(BaseModel):
    """Wallet list item for summary responses"""

    name: str
    network: str
    enterprise_address: str
    is_default: bool = Field(default=False)


class WalletListResponse(BaseModel):
    """List of wallets response"""

    wallets: list[WalletListItem]
    total: int = Field(description="Total number of wallets")
    default_wallet: str | None = Field(None, description="Name of the default wallet")


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


class SwitchWalletRequest(BaseModel):
    """Request to switch the active wallet"""

    wallet_name: str = Field(description="Name of the wallet to switch to")


class SwitchWalletResponse(BaseModel):
    """Response for wallet switch operation"""

    success: bool
    message: str
    active_wallet: str | None = Field(None, description="Name of the now-active wallet")


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
