"""
Transaction Schemas

Pydantic models for transaction-related API requests and responses.
"""

from datetime import datetime

from pydantic import BaseModel, Field

from api.enums import TransactionStatus, TransactionType


# ============================================================================
# Send ADA Request/Response Schemas
# ============================================================================


class SendAdaRequest(BaseModel):
    """
    Request to send ADA to an address.

    The source wallet is determined from the JWT token in the Authorization header.
    Use the /wallets/{wallet_id}/unlock endpoint to get a token first.
    """

    from_address_index: int = Field(default=0, ge=0, le=100, description="Source address index (0 = main address)")
    to_address: str = Field(description="Destination Cardano address")
    amount_ada: float = Field(gt=0, description="Amount in ADA to send (must be > 0)")


class SendAdaResponse(BaseModel):
    """Response for send ADA operation"""

    success: bool
    tx_hash: str | None = Field(None, description="Transaction hash")
    explorer_url: str | None = Field(None, description="Blockchain explorer URL")
    from_address: str | None = Field(None, description="Source address used")
    to_address: str | None = Field(None, description="Destination address")
    amount_lovelace: int | None = Field(None, description="Amount sent in lovelace")
    amount_ada: float | None = Field(None, description="Amount sent in ADA")
    fee_lovelace: int | None = Field(None, description="Transaction fee in lovelace")
    fee_ada: float | None = Field(None, description="Transaction fee in ADA")
    submitted_at: datetime | None = Field(None, description="When the transaction was submitted")
    error: str | None = Field(None, description="Error message if failed")


# ============================================================================
# Transaction Status Schemas
# ============================================================================


class TransactionStatusResponse(BaseModel):
    """Response for transaction status query"""

    tx_hash: str = Field(description="Transaction hash")
    status: TransactionStatus = Field(description="Current transaction status")
    confirmations: int | None = Field(None, description="Number of confirmations (if confirmed)")
    block_height: int | None = Field(None, description="Block height (if confirmed)")
    block_time: datetime | None = Field(None, description="Block timestamp (if confirmed)")
    fee_lovelace: int | None = Field(None, description="Transaction fee in lovelace")
    explorer_url: str = Field(description="Blockchain explorer URL")
    submitted_at: datetime | None = Field(None, description="When submitted to network")
    confirmed_at: datetime | None = Field(None, description="When confirmed on-chain")


# ============================================================================
# Transaction History Schemas
# ============================================================================


class TransactionHistoryItem(BaseModel):
    """Single transaction in history"""

    id: str = Field(description="Database record ID (MongoDB ObjectId)")
    tx_hash: str = Field(description="Transaction hash")
    tx_type: str = Field(
        description="Type of transaction - Common values: send_ada, mint_token, mint_protocol, burn_token, stake, unstake, smart_contract"
    )
    status: TransactionStatus = Field(
        description="Current status - Possible values: BUILT, SIGNED, PENDING, SUBMITTED, CONFIRMED, FAILED"
    )
    from_address: str | None = Field(None, description="Source address")
    to_address: str | None = Field(None, description="Destination address")
    amount_lovelace: int | None = Field(None, description="Amount in lovelace")
    amount_ada: float | None = Field(None, description="Amount in ADA")
    fee_lovelace: int | None = Field(None, description="Fee in lovelace")
    explorer_url: str | None = Field(None, description="Explorer URL")
    submitted_at: datetime | None = Field(None, description="Submission timestamp")
    confirmed_at: datetime | None = Field(None, description="Confirmation timestamp")
    metadata: dict | None = Field(None, description="Additional metadata")


class TransactionHistoryRequest(BaseModel):
    """Request parameters for transaction history"""

    wallet_name: str | None = Field(None, description="Filter by wallet name")
    tx_type: TransactionType | None = Field(
        None,
        description="Filter by transaction type (send_ada, mint_token, mint_protocol, burn_token, stake, unstake, smart_contract)"
    )
    status: TransactionStatus | None = Field(
        None,
        description="Filter by status (BUILT, SIGNED, PENDING, SUBMITTED, CONFIRMED, FAILED)"
    )
    from_date: datetime | None = Field(None, description="Filter transactions after this date")
    to_date: datetime | None = Field(None, description="Filter transactions before this date")
    limit: int = Field(default=50, ge=1, le=500, description="Number of results to return (1-500)")
    offset: int = Field(default=0, ge=0, description="Offset for pagination")


class TransactionHistoryResponse(BaseModel):
    """Response with transaction history"""

    transactions: list[TransactionHistoryItem] = Field(description="List of transactions")
    total: int = Field(description="Total number of transactions matching filters")
    limit: int = Field(description="Limit used in query")
    offset: int = Field(description="Offset used in query")
    has_more: bool = Field(description="Whether more results are available")


# ============================================================================
# Transaction Detail Schema
# ============================================================================


class TransactionInput(BaseModel):
    """Transaction input information"""

    tx_id: str = Field(description="Input transaction ID")
    output_index: int = Field(description="Output index")
    address: str = Field(description="Address")
    amount_lovelace: int = Field(description="Amount in lovelace")


class TransactionOutput(BaseModel):
    """Transaction output information"""

    address: str = Field(description="Destination address")
    amount_lovelace: int = Field(description="Amount in lovelace")
    amount_ada: float = Field(description="Amount in ADA")
    assets: dict | None = Field(None, description="Multi-assets if any")


class TransactionDetailResponse(BaseModel):
    """Detailed transaction information"""

    tx_hash: str = Field(description="Transaction hash")
    status: TransactionStatus = Field(description="Current status")
    tx_type: str | None = Field(None, description="Transaction type (operation)")

    inputs: list[TransactionInput] = Field(default_factory=list, description="Transaction inputs")
    outputs: list[TransactionOutput] = Field(default_factory=list, description="Transaction outputs")

    fee_lovelace: int | None = Field(None, description="Transaction fee in lovelace")
    fee_ada: float | None = Field(None, description="Transaction fee in ADA")

    block_height: int | None = Field(None, description="Block height (if confirmed)")
    block_time: datetime | None = Field(None, description="Block timestamp (if confirmed)")
    confirmations: int | None = Field(None, description="Number of confirmations")

    metadata: dict | None = Field(None, description="Transaction metadata")

    submitted_at: datetime | None = Field(None, description="Submission timestamp")
    confirmed_at: datetime | None = Field(None, description="Confirmation timestamp")

    explorer_url: str = Field(description="Blockchain explorer URL")


# ============================================================================
# Min Lovelace Calculation Schemas
# ============================================================================


class MultiAssetItem(BaseModel):
    """Multi-asset (native token) item for min lovelace calculation"""

    policyid: str = Field(description="Policy ID (hex string)")
    tokens: dict[str, int] = Field(description="Token names mapped to amounts. Key: token name (hex or string), Value: quantity")


class AddressDestin(BaseModel):
    """
    Request to calculate minimum lovelace for a UTXO output.

    Used to determine the minimum ADA required for a UTXO based on:
    - Address size
    - Native tokens (multiAsset) if present
    - Datum if present
    - Current protocol parameters

    **Datum Format Options:**
    - String: CBOR hex string (e.g., "d8799f00ff")
    - Dict: JSON object with constructor and fields (e.g., {"constructor": 0, "fields": []})
    - Null: No datum attached
    """

    address: str = Field(description="Destination Cardano address")
    lovelace: int = Field(default=0, ge=0, description="Initial lovelace amount (usually 0 for min calculation)")
    multiAsset: list[MultiAssetItem] | None = Field(None, description="Native tokens (if any)")
    datum: str | dict | None = Field(
        None,
        description="Datum in CBOR hex format (string) OR as a dict object. Examples: '585d...' or {'constructor': 0, 'fields': []}",
    )


class MinLovelaceResponse(BaseModel):
    """Response for min lovelace calculation"""

    min_lovelace: int = Field(description="Minimum lovelace required for the UTXO")
    min_ada: float = Field(description="Minimum ADA required (lovelace / 1,000,000)")


# ============================================================================
# Blockchain Transaction History Schemas
# ============================================================================


class BlockchainAssetItem(BaseModel):
    """Native asset in a transaction input/output"""

    policy_id: str = Field(description="Asset policy ID")
    asset_name: str = Field(description="Asset name (hex)")
    asset_name_label: str | None = Field(None, description="Decoded asset name if possible")
    quantity: str = Field(description="Asset quantity (as string to handle large numbers)")
    fingerprint: str | None = Field(None, description="Asset fingerprint")


class BlockchainTransactionInput(BaseModel):
    """Transaction input from blockchain query"""

    address: str = Field(description="Input address")
    tx_hash: str = Field(description="Transaction hash of the output being spent")
    output_index: int = Field(description="Output index being spent")
    amount: list[dict] = Field(description="Amount including ADA and native assets")
    collateral: bool = Field(default=False, description="Whether this is a collateral input")
    data_hash: str | None = Field(None, description="Datum hash if present")
    inline_datum: str | None = Field(None, description="Inline datum if present")
    reference_script_hash: str | None = Field(None, description="Reference script hash if present")


class BlockchainTransactionOutput(BaseModel):
    """Transaction output from blockchain query"""

    address: str = Field(description="Output address")
    amount: list[dict] = Field(description="Amount including ADA and native assets")
    output_index: int = Field(description="Output index in transaction")
    data_hash: str | None = Field(None, description="Datum hash if present")
    inline_datum: str | None = Field(None, description="Inline datum if present")
    collateral: bool = Field(default=False, description="Whether this is a collateral output")
    reference_script_hash: str | None = Field(None, description="Reference script hash if present")


class BlockchainTransactionItem(BaseModel):
    """
    Transaction item from blockchain query.

    Enriched with full UTXO details, fees, size, and metadata.
    Follows the pattern from the user's reference implementation.
    """

    # Transaction identification
    hash: str = Field(description="Transaction hash")

    # Block information
    block_height: int = Field(description="Block height where transaction was confirmed")
    block_time: int = Field(description="Block timestamp (Unix time)")
    block: str = Field(description="Block hash")
    slot: int = Field(description="Slot number")

    # Transaction details
    inputs: list[BlockchainTransactionInput] = Field(description="Transaction inputs")
    outputs: list[BlockchainTransactionOutput] = Field(description="Transaction outputs")

    # Fees and size
    fees: str = Field(description="Transaction fees in lovelace")
    size: int = Field(description="Transaction size in bytes")

    # Additional information
    index: int = Field(description="Transaction index in block")
    output_amount: list[dict] = Field(description="Total output amounts")
    deposit: str = Field(description="Deposit amount in lovelace")

    # Metadata
    metadata: list[dict] | None = Field(None, description="Transaction metadata")

    # Validation
    invalid_before: str | None = Field(None, description="Invalid before slot")
    invalid_hereafter: str | None = Field(None, description="Invalid after slot")
    valid_contract: bool = Field(default=True, description="Whether contract validation passed")

    # Explorer URL
    explorer_url: str = Field(description="Blockchain explorer URL")


class BlockchainTransactionHistoryResponse(BaseModel):
    """Response for blockchain transaction history query"""

    transactions: list[BlockchainTransactionItem] = Field(description="List of blockchain transactions")
    total: int = Field(description="Total number of transactions returned")
    page: int = Field(description="Current page number")
    limit: int = Field(description="Results per page")
    has_more: bool = Field(description="Whether more results are available")


# ============================================================================
# Two-Stage Transaction Flow Schemas
# ============================================================================


class BuildTransactionRequest(BaseModel):
    """
    Request to build an unsigned transaction.

    The source wallet is determined from the JWT token.
    No password required for building - just queries chain state.

    Metadata formats supported:
    - CIP-20: {"msg": "Your message here"} or {"msg": ["chunk1", "chunk2"]}
    - Custom: {"1337": {"app": "MyApp", "data": {...}}}
    """

    from_address_index: int = Field(default=0, ge=0, le=100, description="Source address index (0 = main address)")
    to_address: str = Field(description="Destination Cardano address")
    amount_ada: float = Field(gt=0, description="Amount in ADA to send (must be > 0)")
    metadata: dict | None = Field(
        None,
        description="Optional transaction metadata (CIP-20 or custom format). "
                    "CIP-20 example: {'msg': 'Hello'}. "
                    "Custom example: {'1337': {'app': 'Terrasacha', 'data': {...}}}"
    )

    class Config:
        json_schema_extra = {
            "example": {
                "from_address_index": 0,
                "to_address": "addr_test1qz...",
                "amount_ada": 10.5,
                "metadata": {
                    "msg": "Carbon credit transaction for Project XYZ"
                }
            }
        }


class BuildTransactionResponse(BaseModel):
    """Response after building an unsigned transaction"""

    success: bool = Field(default=True)
    transaction_id: str = Field(description="Unique transaction ID for signing/submitting")
    tx_hash: str | None = Field(description="Transaction hash (calculated from unsigned tx)")
    tx_cbor: str = Field(description="Unsigned transaction CBOR hex")
    from_address: str = Field(description="Source address used")
    to_address: str = Field(description="Destination address")
    amount_lovelace: int = Field(description="Amount being sent in lovelace")
    amount_ada: float = Field(description="Amount being sent in ADA")
    estimated_fee_lovelace: int = Field(description="Estimated transaction fee in lovelace")
    estimated_fee_ada: float = Field(description="Estimated transaction fee in ADA")
    metadata: dict | None = Field(None, description="Transaction metadata (if provided)")
    status: str = Field(default="BUILT", description="Transaction status")

    class Config:
        json_schema_extra = {
            "example": {
                "success": True,
                "transaction_id": "6994b691d6c64fd141eee2d4380251730b44c99da599b82f14c3d29514ede38f",
                "tx_hash": "6994b691d6c64fd141eee2d4380251730b44c99da599b82f14c3d29514ede38f",
                "tx_cbor": "84a4...",
                "from_address": "addr_test1vz...",
                "to_address": "addr_test1qz...",
                "amount_lovelace": 10500000,
                "amount_ada": 10.5,
                "estimated_fee_lovelace": 170000,
                "estimated_fee_ada": 0.17,
                "status": "BUILT"
            }
        }


class SignTransactionRequest(BaseModel):
    """
    Request to sign a built transaction.

    Requires the wallet password to decrypt the mnemonic and sign.
    """

    transaction_id: str = Field(description="Transaction ID from build endpoint")
    password: str = Field(min_length=1, description="Wallet password")

    class Config:
        json_schema_extra = {
            "example": {
                "transaction_id": "6994b691d6c64fd141eee2d4380251730b44c99da599b82f14c3d29514ede38f",
                "password": "MySecureP@ssw0rd"
            }
        }


class SignTransactionResponse(BaseModel):
    """Response after signing a transaction"""

    success: bool = Field(default=True)
    transaction_id: str = Field(description="Transaction ID")
    signed_tx_cbor: str = Field(description="Signed transaction CBOR hex")
    tx_hash: str = Field(description="Transaction hash")
    status: str = Field(default="SIGNED", description="Transaction status")

    class Config:
        json_schema_extra = {
            "example": {
                "success": True,
                "transaction_id": "6994b691d6c64fd141eee2d4380251730b44c99da599b82f14c3d29514ede38f",
                "signed_tx_cbor": "84a5...",
                "tx_hash": "6994b691d6c64fd141eee2d4380251730b44c99da599b82f14c3d29514ede38f",
                "status": "SIGNED"
            }
        }


class SubmitTransactionRequest(BaseModel):
    """
    Request to submit a signed transaction to the blockchain.

    No password required - transaction must already be signed.
    """

    transaction_id: str = Field(description="Transaction ID from sign endpoint")

    class Config:
        json_schema_extra = {
            "example": {
                "transaction_id": "123e4567-e89b-12d3-a456-426614174000"
            }
        }


class SubmitTransactionResponse(BaseModel):
    """Response after submitting a transaction"""

    success: bool = Field(default=True)
    transaction_id: str = Field(description="Transaction ID")
    tx_hash: str = Field(description="Transaction hash")
    status: str = Field(default="SUBMITTED", description="Transaction status")
    submitted_at: datetime = Field(description="When the transaction was submitted")
    explorer_url: str | None = Field(None, description="Blockchain explorer URL")

    class Config:
        json_schema_extra = {
            "example": {
                "success": True,
                "transaction_id": "6994b691d6c64fd141eee2d4380251730b44c99da599b82f14c3d29514ede38f",
                "tx_hash": "abc123def456...",
                "status": "SUBMITTED",
                "submitted_at": "2025-11-14T12:00:00Z",
                "explorer_url": "https://preview.cardanoscan.io/transaction/abc123..."
            }
        }


class SignAndSubmitTransactionRequest(BaseModel):
    """
    Request to sign AND submit a transaction in one operation (convenience endpoint).

    Requires the wallet password to decrypt the mnemonic and sign.
    After signing, immediately submits to blockchain.
    """

    transaction_id: str = Field(description="Transaction ID from build endpoint")
    password: str = Field(min_length=1, description="Wallet password")

    class Config:
        json_schema_extra = {
            "example": {
                "transaction_id": "6994b691d6c64fd141eee2d4380251730b44c99da599b82f14c3d29514ede38f",
                "password": "MySecureP@ssw0rd"
            }
        }


class SignAndSubmitTransactionResponse(BaseModel):
    """Response after signing and submitting a transaction"""

    success: bool = Field(default=True)
    transaction_id: str = Field(description="Transaction ID")
    tx_hash: str = Field(description="Transaction hash")
    status: str = Field(default="SUBMITTED", description="Transaction status")
    signed_at: datetime = Field(description="When the transaction was signed")
    submitted_at: datetime = Field(description="When the transaction was submitted")
    explorer_url: str | None = Field(None, description="Blockchain explorer URL")

    class Config:
        json_schema_extra = {
            "example": {
                "success": True,
                "transaction_id": "6994b691d6c64fd141eee2d4380251730b44c99da599b82f14c3d29514ede38f",
                "tx_hash": "abc123def456...",
                "status": "SUBMITTED",
                "signed_at": "2025-11-14T12:00:00Z",
                "submitted_at": "2025-11-14T12:00:01Z",
                "explorer_url": "https://preview.cardanoscan.io/transaction/abc123..."
            }
        }


# ============================================================================
# Error Response Schema
# ============================================================================


class TransactionErrorResponse(BaseModel):
    """Error response for transaction operations"""

    success: bool = Field(default=False)
    error: str = Field(description="Error message")
    error_code: str | None = Field(None, description="Error code")
    details: dict | None = Field(None, description="Additional error details")
