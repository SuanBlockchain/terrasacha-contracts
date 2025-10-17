"""
Contract Schemas

Pydantic models for contract-related API requests and responses.
"""

from datetime import datetime
from enum import Enum

from pydantic import BaseModel, Field


# ============================================================================
# Enums
# ============================================================================


class ContractType(str, Enum):
    """Contract type enumeration"""

    MINTING_POLICY = "minting_policy"
    SPENDING_VALIDATOR = "spending_validator"


class ContractStorageType(str, Enum):
    """Contract storage type"""

    LOCAL = "local"
    REFERENCE_SCRIPT = "reference_script"


# ============================================================================
# Compilation Request/Response Schemas
# ============================================================================


class CompileProtocolRequest(BaseModel):
    """Request to compile protocol contracts"""

    wallet_name: str | None = Field(
        default=None, description="Wallet to use for UTXO (default wallet if not specified)"
    )
    force: bool = Field(default=False, description="Force recompilation even if contracts exist")


class CompileProtocolResponse(BaseModel):
    """Response for protocol compilation"""

    success: bool
    message: str | None = None
    contracts: list[str] | None = Field(None, description="List of compiled contract names")
    protocol_policy_id: str | None = Field(None, description="Protocol validator policy ID")
    protocol_nfts_policy_id: str | None = Field(None, description="Protocol NFTs minting policy ID")
    compilation_utxo: dict | None = Field(None, description="UTXO used for compilation")
    skipped: bool = Field(False, description="Whether compilation was skipped (already exists)")
    error: str | None = Field(None, description="Error message if failed")


class CompileProjectRequest(BaseModel):
    """Request to compile project contracts"""

    wallet_name: str | None = Field(
        default=None, description="Wallet to use for UTXO (default wallet if not specified)"
    )


class CompileProjectResponse(BaseModel):
    """Response for project compilation"""

    success: bool
    message: str | None = None
    project_name: str | None = Field(None, description="Name of the compiled project contract")
    project_nfts_name: str | None = Field(None, description="Name of the project NFTs minting policy")
    project_policy_id: str | None = Field(None, description="Project validator policy ID")
    project_nfts_policy_id: str | None = Field(None, description="Project NFTs minting policy ID")
    used_utxo: str | None = Field(None, description="UTXO reference used for compilation")
    saved: bool = Field(False, description="Whether contracts were saved to disk")
    error: str | None = Field(None, description="Error message if failed")


class CompileGreyRequest(BaseModel):
    """Request to compile grey token contract"""

    project_name: str = Field(description="Name of the project to compile grey contract for")


class CompileGreyResponse(BaseModel):
    """Response for grey token compilation"""

    success: bool
    message: str | None = None
    grey_contract_name: str | None = Field(None, description="Name of the grey token contract")
    grey_policy_id: str | None = Field(None, description="Grey token minting policy ID")
    project_name: str | None = Field(None, description="Associated project name")
    project_nfts_policy_id: str | None = Field(None, description="Project NFTs policy ID used")
    saved: bool = Field(False, description="Whether contract was saved to disk")
    error: str | None = Field(None, description="Error message if failed")


class CompileInvestorRequest(BaseModel):
    """Request to compile investor contract"""

    project_name: str = Field(description="Name of the project to compile investor contract for")


class CompileInvestorResponse(BaseModel):
    """Response for investor compilation"""

    success: bool
    message: str | None = None
    investor_contract_name: str | None = Field(None, description="Name of the investor contract")
    investor_address: str | None = Field(None, description="Investor contract address")
    project_name: str | None = Field(None, description="Associated project name")
    protocol_policy_id: str | None = Field(None, description="Protocol policy ID used")
    grey_policy_id: str | None = Field(None, description="Grey token policy ID used")
    grey_token_name: str | None = Field(None, description="Grey token name used")
    saved: bool = Field(False, description="Whether contract was saved to disk")
    error: str | None = Field(None, description="Error message if failed")


# ============================================================================
# Contract Info Schemas
# ============================================================================


class ContractListItem(BaseModel):
    """Single contract in list"""

    name: str = Field(description="Contract name")
    policy_id: str = Field(description="Contract policy ID or script hash")
    contract_type: ContractType = Field(description="Type of contract")
    address: str | None = Field(None, description="Contract address (spending validators only)")
    balance_lovelace: int | None = Field(None, description="Balance in lovelace (spending validators only)")
    balance_ada: float | None = Field(None, description="Balance in ADA (spending validators only)")


class ContractListResponse(BaseModel):
    """Response with list of contracts"""

    contracts: list[ContractListItem] = Field(description="List of compiled contracts")
    total: int = Field(description="Total number of contracts")
    compilation_utxo: dict | None = Field(None, description="Protocol compilation UTXO info")


class ContractDetailResponse(BaseModel):
    """Detailed contract information"""

    name: str = Field(description="Contract name")
    policy_id: str = Field(description="Contract policy ID or script hash")
    contract_type: ContractType = Field(description="Type of contract")
    storage_type: ContractStorageType = Field(description="How the contract is stored")
    testnet_address: str = Field(description="Testnet address")
    mainnet_address: str = Field(description="Mainnet address")
    balance_lovelace: int | None = Field(None, description="Current balance in lovelace")
    balance_ada: float | None = Field(None, description="Current balance in ADA")
    compilation_utxo: dict | None = Field(None, description="UTXO used for compilation")
    reference_utxo: dict | None = Field(None, description="Reference script UTXO info (if reference script)")


class ContractInfoResponse(BaseModel):
    """Comprehensive contract information (similar to CLI display)"""

    contracts: dict[str, dict] = Field(description="Contract information keyed by name")
    compilation_utxo: dict | None = Field(None, description="Protocol compilation UTXO")
    total_contracts: int = Field(description="Total number of compiled contracts")


# ============================================================================
# Datum Schemas
# ============================================================================


class ProtocolDatum(BaseModel):
    """Protocol contract datum"""

    project_admins: list[str] = Field(description="List of admin PKH hex strings")
    protocol_fee: int = Field(description="Protocol fee in lovelace")
    oracle_id: str = Field(description="Oracle policy ID hex")
    projects: list[str] = Field(description="List of project ID hashes")


class ProjectTokenInfo(BaseModel):
    """Project token information"""

    policy_id: str = Field(description="Token policy ID hex")
    token_name: str = Field(description="Token name hex")
    total_supply: int = Field(description="Total supply of tokens")


class ProjectParams(BaseModel):
    """Project parameters"""

    project_id: str = Field(description="Project ID hex")
    project_metadata: str = Field(description="Project metadata hex")
    project_state: int = Field(description="Project state (0-3)")


class StakeholderInfo(BaseModel):
    """Stakeholder information"""

    stakeholder: str = Field(description="Stakeholder name hex")
    pkh: str = Field(description="Public key hash hex")
    participation: int = Field(description="Grey token allocation")
    claimed: str = Field(description="Whether claimed (True/False)")


class CertificationInfo(BaseModel):
    """Certification information"""

    certification_date: int = Field(description="Certification date (POSIX timestamp)")
    quantity: int = Field(description="Promised carbon credits")
    real_certification_date: int = Field(description="Actual certification date")
    real_quantity: int = Field(description="Actual verified carbon credits")


class ProjectDatum(BaseModel):
    """Project contract datum"""

    params: ProjectParams
    project_token: ProjectTokenInfo
    stakeholders: list[StakeholderInfo]
    certifications: list[CertificationInfo]


class PriceWithPrecision(BaseModel):
    """Price with precision"""

    price: int = Field(description="Price value")
    precision: int = Field(description="Decimal precision")


class InvestorDatum(BaseModel):
    """Investor contract datum"""

    seller_pkh: str = Field(description="Seller public key hash hex")
    grey_token_amount: int = Field(description="Amount of grey tokens for sale")
    price_per_token: PriceWithPrecision = Field(description="Price per token with precision")
    min_purchase_amount: int = Field(description="Minimum purchase amount")


class ContractDatumResponse(BaseModel):
    """Response for contract datum query"""

    success: bool
    contract_name: str | None = Field(None, description="Contract name")
    contract_type: str | None = Field(None, description="Contract type (protocol, project, investor)")
    datum: ProtocolDatum | ProjectDatum | InvestorDatum | None = Field(None, description="Decoded datum data")
    utxo_ref: str | None = Field(None, description="UTXO reference (tx_id:index)")
    balance_lovelace: int | None = Field(None, description="UTXO balance in lovelace")
    balance_ada: float | None = Field(None, description="UTXO balance in ADA")
    error: str | None = Field(None, description="Error message if failed")


# ============================================================================
# Error Response Schema
# ============================================================================


class ContractErrorResponse(BaseModel):
    """Error response for contract operations"""

    success: bool = Field(default=False)
    error: str = Field(description="Error message")
    error_code: str | None = Field(None, description="Error code")
    details: dict | None = Field(None, description="Additional error details")
