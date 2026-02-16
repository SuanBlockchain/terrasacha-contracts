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


class AvailableContractInfo(BaseModel):
    """Information about an available contract"""

    name: str = Field(description="Contract name")
    file_path: str = Field(description="File path relative to src/terrasacha_contracts/")
    description: str = Field(description="Human-readable description")
    category: str = Field(description="Contract category (core_protocol, project_management, token_management, testing)")
    requires_params: bool = Field(description="Whether compilation requires parameters")
    param_description: str | None = Field(None, description="Description of required parameters")
    tags: list[str] | None = Field(None, description="Optional tags for filtering and discovery")


class AvailableContractsResponse(BaseModel):
    """Response with available contracts for compilation"""

    minting: list[AvailableContractInfo] = Field(description="Available minting policy contracts")
    spending: list[AvailableContractInfo] = Field(description="Available spending validator contracts")
    total: int = Field(description="Total number of available contracts")


class CompileContractRequest(BaseModel):
    """
    Request to compile a registry contract.

    Compiles pre-defined contracts from the contract registry.
    Use GET /api/v1/contracts/available to see available contracts.
    """

    contract_name: str = Field(description="Name of the contract from registry (e.g., 'protocol', 'myUSDFree', 'grey')")
    contract_type: str = Field(
        description="Contract type: 'spending' for validators or 'minting' for policies"
    )
    compilation_params: list | None = Field(
        None,
        description="Optional compilation parameters for parameterized contracts (e.g., policy IDs, UTXOs)"
    )

    class Config:
        json_schema_extra = {
            "example": {
                "contract_name": "myUSDFree",
                "contract_type": "minting"
            }
        }


class CompileCustomContractRequest(BaseModel):
    """
    Request to compile a custom contract from source code.

    Allows CORE wallets to compile custom Opshin smart contracts.
    Requires tenant permission (allow_custom_contracts = true).
    """

    contract_name: str = Field(description="Custom name for your contract (e.g., 'my_custom_validator')")
    contract_type: str = Field(
        description="Contract type: 'spending' for validators or 'minting' for policies"
    )
    source_code: str = Field(
        description=(
            "Opshin source code for the contract. "
            "Must start with '#!opshin' shebang. "
            "For spending validators: def validator(datum, redeemer, context). "
            "For minting policies: def validator(redeemer, context)."
        )
    )

    class Config:
        json_schema_extra = {
            "example": {
                "contract_name": "my_test_validator",
                "contract_type": "spending",
                "source_code": "#!opshin\nfrom opshin.prelude import *\n\ndef validator(datum: Nothing, redeemer: Nothing, context: ScriptContext) -> None:\n    \"\"\"Always succeeds - for testing only\"\"\"\n    assert True, \"Always succeeds\""
            }
        }


class CompileContractResponse(BaseModel):
    """Response after contract compilation"""

    success: bool = Field(default=True)
    policy_id: str = Field(description="Contract policy ID (primary key / script hash)")
    contract_name: str = Field(description="Contract name")
    description: str | None = Field(None, description="Contract description (from registry for pre-defined contracts, None for custom)")
    cbor_hex: str = Field(description="Compiled CBOR hex string")
    testnet_address: str | None = Field(None, description="Testnet address")
    mainnet_address: str | None = Field(None, description="Mainnet address")
    contract_type: str = Field(description="Contract type (spending/minting)")
    source_hash: str = Field(description="SHA256 hash of source code (for versioning)")
    version: int = Field(description="Contract version (auto-increments on recompile)")
    compiled_at: datetime = Field(description="Compilation timestamp")
    category: str | None = Field(None, description="Contract category from registry (None for custom contracts)")
    is_custom_contract: bool = Field(False, description="True if compiled from custom source (not in registry)")
    is_active: bool = Field(True, description="Whether the contract is still active (False after burn invalidation)")
    invalidated_at: datetime | None = Field(None, description="When contract was invalidated (None if still active)")

    class Config:
        json_schema_extra = {
            "example": {
                "success": True,
                "policy_id": "a1b2c3d4e5f6...",
                "contract_name": "my_validator",
                "cbor_hex": "590abc...",
                "testnet_address": "addr_test1wz...",
                "mainnet_address": "addr1w9...",
                "contract_type": "spending",
                "source_hash": "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855",
                "version": 1,
                "compiled_at": "2025-11-16T12:00:00Z"
            }
        }


class CompileProtocolRequest(BaseModel):
    """Request to compile protocol contracts (protocol_nfts and protocol)"""

    wallet_id: str | None = Field(
        default=None,
        description="Wallet ID to use for UTXO source. If not provided, uses the authenticated CORE wallet."
    )
    utxo_ref: str | None = Field(
        default=None,
        description="Specific UTXO reference (tx_hash:index) to use for compilation. If not provided, auto-selects a suitable UTXO with >3 ADA."
    )
    force: bool = Field(
        default=False,
        description="Force recompilation even if contracts with same parameters already exist."
    )

    class Config:
        json_schema_extra = {
            "example": {
                "wallet_id": "2337a77234f62a7ff63e4ca933c54918746bdddd295110d400d0110e",
                "utxo_ref": "abc123...def:0",
                "force": False
            }
        }


class CompilationUtxoInfo(BaseModel):
    """Information about the UTXO used for contract compilation"""

    tx_id: str = Field(description="Transaction ID (hex)")
    index: int = Field(description="Output index")
    amount_lovelace: int = Field(description="Amount in lovelace")
    amount_ada: float = Field(description="Amount in ADA")


class CompiledProtocolContractInfo(BaseModel):
    """Information about a compiled protocol contract"""

    policy_id: str = Field(description="Contract policy ID (script hash)")
    contract_name: str = Field(description="Contract name")
    contract_type: str = Field(description="Contract type (minting/spending)")
    cbor_hex: str = Field(description="Compiled CBOR hex string")
    testnet_address: str | None = Field(None, description="Testnet address (for spending validators)")
    mainnet_address: str | None = Field(None, description="Mainnet address (for spending validators)")
    version: int = Field(description="Contract version")
    compiled_at: datetime = Field(description="Compilation timestamp")


class CompileProtocolResponse(BaseModel):
    """Response for protocol contracts compilation"""

    success: bool = Field(description="Whether compilation succeeded")
    message: str = Field(description="Status message")

    # Compiled contracts
    protocol_nfts: CompiledProtocolContractInfo | None = Field(
        None, description="Compiled protocol_nfts minting policy"
    )
    protocol: CompiledProtocolContractInfo | None = Field(
        None, description="Compiled protocol spending validator"
    )

    # Compilation metadata
    compilation_utxo: CompilationUtxoInfo | None = Field(
        None, description="UTXO used for contract compilation (determines uniqueness)"
    )

    # Status flags
    skipped: bool = Field(False, description="Whether compilation was skipped (contracts already exist)")
    error: str | None = Field(None, description="Error message if failed")

    class Config:
        json_schema_extra = {
            "example": {
                "success": True,
                "message": "Successfully compiled 2 protocol contracts",
                "protocol_nfts": {
                    "policy_id": "abc123...",
                    "contract_name": "protocol_nfts",
                    "contract_type": "minting",
                    "cbor_hex": "590abc...",
                    "version": 1,
                    "compiled_at": "2025-01-27T12:00:00Z"
                },
                "protocol": {
                    "policy_id": "def456...",
                    "contract_name": "protocol",
                    "contract_type": "spending",
                    "cbor_hex": "590def...",
                    "testnet_address": "addr_test1...",
                    "mainnet_address": "addr1...",
                    "version": 1,
                    "compiled_at": "2025-01-27T12:00:00Z"
                },
                "compilation_utxo": {
                    "tx_id": "abc123...",
                    "index": 0,
                    "amount_lovelace": 5000000,
                    "amount_ada": 5.0
                },
                "skipped": False
            }
        }


class MintProtocolRequest(BaseModel):
    """Request to build an unsigned minting transaction for protocol NFTs"""

    protocol_nfts_policy_id: str = Field(
        description=(
            "Policy ID of the compiled protocol_nfts minting policy to use. "
            "Obtained from the compile-protocol response or GET /contracts/."
        )
    )
    wallet_id: str | None = Field(
        default=None,
        description=(
            "Wallet ID whose UTXO was used during compilation. "
            "If not provided, uses the authenticated CORE wallet."
        )
    )
    destination_address: str | None = Field(
        default=None,
        description="Address to send USER token to. If not provided, uses the wallet address."
    )

    class Config:
        json_schema_extra = {
            "example": {
                "protocol_nfts_policy_id": "abc123def456...",
                "wallet_id": "2337a77234f62a7ff63e4ca933c54918746bdddd295110d400d0110e",
                "destination_address": "addr_test1qz..."
            }
        }


class MintProtocolResponse(BaseModel):
    """Response after building an unsigned minting transaction for protocol NFTs"""

    success: bool = Field(default=True)
    transaction_id: str = Field(description="Transaction hash (use for sign/submit)")
    tx_cbor: str = Field(description="Unsigned transaction body CBOR hex")
    protocol_token_name: str = Field(description="Hex name of minted REF token")
    user_token_name: str = Field(description="Hex name of minted USER token")
    minting_policy_id: str = Field(description="Protocol NFTs minting policy ID")
    protocol_contract_address: str = Field(description="Address where REF token is sent")
    compilation_utxo: CompilationUtxoInfo = Field(description="UTXO being consumed in the mint")
    fee_lovelace: int = Field(description="Estimated transaction fee in lovelace")
    inputs: list[dict] = Field(description="Transaction inputs")
    outputs: list[dict] = Field(description="Transaction outputs")

    class Config:
        json_schema_extra = {
            "example": {
                "success": True,
                "transaction_id": "abc123...def",
                "tx_cbor": "84a400...",
                "protocol_token_name": "5245465f...",
                "user_token_name": "555345525f...",
                "minting_policy_id": "abc123...",
                "protocol_contract_address": "addr_test1wz...",
                "compilation_utxo": {
                    "tx_id": "abc123...",
                    "index": 0,
                    "amount_lovelace": 5000000,
                    "amount_ada": 5.0
                },
                "fee_lovelace": 300000,
                "inputs": [],
                "outputs": []
            }
        }


class BurnProtocolRequest(BaseModel):
    """Request to build an unsigned burn transaction for protocol NFTs"""

    protocol_nfts_policy_id: str = Field(
        description=(
            "Policy ID of the protocol_nfts minting policy whose tokens to burn. "
            "Obtained from the compile-protocol response or GET /contracts/."
        )
    )
    wallet_id: str | None = Field(
        default=None,
        description=(
            "Wallet ID holding the USER token. "
            "If not provided, uses the authenticated CORE wallet."
        )
    )

    class Config:
        json_schema_extra = {
            "example": {
                "protocol_nfts_policy_id": "abc123def456...",
                "wallet_id": "2337a77234f62a7ff63e4ca933c54918746bdddd295110d400d0110e",
            }
        }


class BurnProtocolResponse(BaseModel):
    """Response after building an unsigned burn transaction for protocol NFTs"""

    success: bool = Field(default=True)
    transaction_id: str = Field(description="Transaction hash (use for sign/submit)")
    tx_cbor: str = Field(description="Unsigned transaction body CBOR hex")
    protocol_token_name: str = Field(description="Hex name of REF token being burned")
    user_token_name: str = Field(description="Hex name of USER token being burned")
    minting_policy_id: str = Field(description="Protocol NFTs minting policy ID")
    protocol_contract_address: str = Field(description="Address where REF token was held")
    fee_lovelace: int = Field(description="Estimated transaction fee in lovelace")
    inputs: list[dict] = Field(description="Transaction inputs")
    outputs: list[dict] = Field(description="Transaction outputs")

    class Config:
        json_schema_extra = {
            "example": {
                "success": True,
                "transaction_id": "abc123...def",
                "tx_cbor": "84a400...",
                "protocol_token_name": "5245465f...",
                "user_token_name": "555345525f...",
                "minting_policy_id": "abc123...",
                "protocol_contract_address": "addr_test1wz...",
                "fee_lovelace": 400000,
                "inputs": [],
                "outputs": []
            }
        }


class InvalidateContractRequest(BaseModel):
    """Request to invalidate contracts after burn confirmation.

    Works for any contract type: protocol, project, etc.
    Finds the target contract and any dependent contracts compiled with its policy_id.
    """

    policy_id: str = Field(
        description=(
            "Policy ID of the contract to invalidate (typically a minting policy). "
            "Must have a burn transaction in SUBMITTED or CONFIRMED state. "
            "Any contracts compiled with this policy_id as a parameter will also be invalidated."
        )
    )

    class Config:
        json_schema_extra = {
            "example": {
                "policy_id": "abc123def456...",
            }
        }


class InvalidatedContractInfo(BaseModel):
    """Information about an invalidated contract"""

    policy_id: str = Field(description="Contract policy ID (script hash)")
    name: str = Field(description="Contract name")
    contract_type: str = Field(description="Contract type (minting/spending)")


class InvalidateContractResponse(BaseModel):
    """Response after invalidating contracts"""

    success: bool = Field(default=True)
    message: str = Field(description="Status message")
    invalidated_contracts: list[InvalidatedContractInfo] = Field(
        description="List of contracts that were invalidated"
    )
    burn_tx_hash: str = Field(description="Transaction hash of the burn operation")
    burn_tx_status: str = Field(description="Status of the burn transaction")
    invalidated_at: datetime = Field(description="Timestamp when contracts were invalidated")

    class Config:
        json_schema_extra = {
            "example": {
                "success": True,
                "message": "Successfully invalidated 2 contracts",
                "invalidated_contracts": [
                    {
                        "policy_id": "abc123...",
                        "name": "protocol_nfts",
                        "contract_type": "minting",
                    },
                    {
                        "policy_id": "def456...",
                        "name": "protocol",
                        "contract_type": "spending",
                    },
                ],
                "burn_tx_hash": "abc123...def",
                "burn_tx_status": "SUBMITTED",
                "invalidated_at": "2025-01-27T12:00:00Z",
            }
        }


class CompileProjectRequest(BaseModel):
    """Request to compile project contracts (project_nfts and project)"""

    project_name: str = Field(
        description="User-provided project name (e.g. 'reforestation_guaviare'). "
        "Used to name contracts as '{project_name}_nfts' and '{project_name}'."
    )
    protocol_nfts_policy_id: str = Field(
        description="Policy ID of the compiled protocol_nfts minting policy. "
        "Obtained from the compile-protocol response."
    )
    wallet_id: str = Field(
        description="Wallet ID whose UTXOs will be used for compilation. "
        "A UTXO with >3 ADA is required to make the contract unique."
    )
    utxo_ref: str | None = Field(
        default=None,
        description="Specific UTXO reference (tx_hash:index) to use for compilation. "
        "If not provided, auto-selects a suitable UTXO with >3 ADA that hasn't been used for another compilation."
    )
    force: bool = Field(
        default=False,
        description="Force recompilation even if contracts with same parameters already exist."
    )

    class Config:
        json_schema_extra = {
            "example": {
                "project_name": "reforestation_guaviare",
                "protocol_nfts_policy_id": "abc123def456...",
                "wallet_id": "2337a77234f62a7ff63e4ca933c54918746bdddd295110d400d0110e",
                "force": False
            }
        }


class CompileProjectResponse(BaseModel):
    """Response for project contracts compilation"""

    success: bool = Field(description="Whether compilation succeeded")
    message: str = Field(description="Status message")

    # Compiled contracts
    project_nfts: CompiledProtocolContractInfo | None = Field(
        None, description="Compiled project_nfts minting policy"
    )
    project: CompiledProtocolContractInfo | None = Field(
        None, description="Compiled project spending validator"
    )

    # Compilation metadata
    compilation_utxo: CompilationUtxoInfo | None = Field(
        None, description="UTXO used for contract compilation (determines uniqueness)"
    )
    protocol_nfts_policy_id: str | None = Field(
        None, description="Protocol NFTs policy ID used for compilation"
    )
    project_name: str | None = Field(
        None, description="User-provided project name"
    )

    # Status flags
    skipped: bool = Field(False, description="Whether compilation was skipped (contracts already exist)")
    error: str | None = Field(None, description="Error message if failed")

    class Config:
        json_schema_extra = {
            "example": {
                "success": True,
                "message": "Successfully compiled 2 project contracts",
                "project_nfts": {
                    "policy_id": "abc123...",
                    "contract_name": "reforestation_guaviare_nfts",
                    "contract_type": "minting",
                    "cbor_hex": "590abc...",
                    "version": 1,
                    "compiled_at": "2025-01-27T12:00:00Z"
                },
                "project": {
                    "policy_id": "def456...",
                    "contract_name": "reforestation_guaviare",
                    "contract_type": "spending",
                    "cbor_hex": "590def...",
                    "testnet_address": "addr_test1...",
                    "version": 1,
                    "compiled_at": "2025-01-27T12:00:00Z"
                },
                "compilation_utxo": {
                    "tx_id": "abc123...",
                    "index": 0,
                    "amount_lovelace": 5000000,
                    "amount_ada": 5.0
                },
                "protocol_nfts_policy_id": "abc123...",
                "project_name": "reforestation_guaviare",
                "skipped": False
            }
        }


class DeployReferenceScriptRequest(BaseModel):
    """Request to deploy a compiled contract as an on-chain reference script"""

    policy_id: str = Field(
        description="Policy ID of the compiled contract to deploy as a reference script."
    )
    wallet_id: str | None = Field(
        default=None,
        description="Wallet ID to fund the transaction. If not provided, uses the authenticated CORE wallet."
    )
    destination_address: str | None = Field(
        default=None,
        description="Address where the reference script UTXO will be stored. "
        "If not provided, uses the wallet's enterprise address."
    )

    class Config:
        json_schema_extra = {
            "example": {
                "policy_id": "abc123def456...",
                "destination_address": "addr_test1qz..."
            }
        }


class DeployReferenceScriptResponse(BaseModel):
    """Response after building an unsigned reference script deployment transaction"""

    success: bool = Field(default=True)
    transaction_id: str = Field(description="Transaction hash (use for sign/submit)")
    tx_cbor: str = Field(description="Unsigned transaction body CBOR hex")
    contract_policy_id: str = Field(description="Policy ID of the deployed contract")
    contract_name: str = Field(description="Name of the deployed contract")
    destination_address: str = Field(description="Address where reference script UTXO is stored")
    min_lovelace: int = Field(description="ADA locked with the reference script (lovelace)")
    reference_output_index: int = Field(description="Output index containing the reference script")
    fee_lovelace: int = Field(description="Estimated transaction fee in lovelace")
    inputs: list[dict] = Field(description="Transaction inputs")
    outputs: list[dict] = Field(description="Transaction outputs")

    class Config:
        json_schema_extra = {
            "example": {
                "success": True,
                "transaction_id": "abc123...def",
                "tx_cbor": "84a400...",
                "contract_policy_id": "abc123...",
                "contract_name": "reforestation_guaviare",
                "destination_address": "addr_test1qz...",
                "min_lovelace": 15000000,
                "reference_output_index": 0,
                "fee_lovelace": 200000,
                "inputs": [],
                "outputs": []
            }
        }


class ConfirmReferenceScriptRequest(BaseModel):
    """Request to confirm a reference script deployment after tx submission"""

    transaction_id: str = Field(
        description="Transaction hash of the deploy-reference-script transaction. "
        "Must be in SUBMITTED or CONFIRMED state."
    )

    class Config:
        json_schema_extra = {
            "example": {
                "transaction_id": "abc123...def"
            }
        }


class ConfirmReferenceScriptResponse(BaseModel):
    """Response after confirming reference script deployment"""

    success: bool = Field(default=True)
    message: str = Field(description="Status message")
    policy_id: str = Field(description="Contract policy ID")
    contract_name: str = Field(description="Contract name")
    reference_utxo: str = Field(description="Reference script UTXO (tx_hash:output_index)")
    reference_tx_hash: str = Field(description="Transaction hash of the reference script")

    class Config:
        json_schema_extra = {
            "example": {
                "success": True,
                "message": "Reference script deployment confirmed",
                "policy_id": "abc123...",
                "contract_name": "reforestation_guaviare",
                "reference_utxo": "abc123...def:0",
                "reference_tx_hash": "abc123...def"
            }
        }


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
    """Single contract in list (for ContractManager - JSON-based system)"""

    name: str = Field(description="Contract name")
    policy_id: str = Field(description="Contract policy ID or script hash")
    contract_type: ContractType = Field(description="Type of contract")
    address: str | None = Field(None, description="Contract address (spending validators only)")
    balance_lovelace: int | None = Field(None, description="Balance in lovelace (spending validators only)")
    balance_ada: float | None = Field(None, description="Balance in ADA (spending validators only)")


class ContractListResponse(BaseModel):
    """Response with list of contracts (for ContractManager - JSON-based system)"""

    contracts: list[ContractListItem] = Field(description="List of compiled contracts")
    total: int = Field(description="Total number of contracts")
    compilation_utxo: dict | None = Field(None, description="Protocol compilation UTXO info")


class DbContractListItem(BaseModel):
    """Single contract in list (for database-backed system)"""

    policy_id: str = Field(description="Contract policy ID (primary key)")
    name: str = Field(description="Contract name")
    description: str | None = Field(None, description="Contract description (from registry for pre-defined contracts, None for custom)")
    contract_type: str = Field(description="Type of contract (spending/minting)")
    testnet_address: str | None = Field(None, description="Testnet address")
    mainnet_address: str | None = Field(None, description="Mainnet address")
    version: int = Field(description="Contract version (increments on recompile)")
    source_hash: str = Field(description="SHA256 hash of source code")
    compiled_at: datetime = Field(description="Compilation timestamp")
    network: str = Field(description="Network (testnet/mainnet)")
    category: str | None = Field(None, description="Contract category from registry (None for custom contracts)")
    is_custom_contract: bool = Field(False, description="True if compiled from custom source (not in registry)")
    is_active: bool = Field(True, description="Whether the contract is still active (False after burn invalidation)")
    invalidated_at: datetime | None = Field(None, description="When contract was invalidated (None if still active)")


class DbContractListResponse(BaseModel):
    """Response with list of contracts (for database-backed system)"""

    contracts: list[DbContractListItem] = Field(description="List of compiled contracts")
    total: int = Field(description="Total number of contracts")


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
