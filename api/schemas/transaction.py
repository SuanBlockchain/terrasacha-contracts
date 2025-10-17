"""
Transaction Schemas

Pydantic models for transaction-related API requests and responses.
"""

from datetime import datetime

from pydantic import BaseModel, Field

from api.enums import TransactionStatus


# ============================================================================
# Send ADA Request/Response Schemas
# ============================================================================


class SendAdaRequest(BaseModel):
    """Request to send ADA to an address"""

    from_wallet: str = Field(description="Source wallet name")
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

    id: int = Field(description="Database record ID")
    tx_hash: str = Field(description="Transaction hash")
    tx_type: str = Field(description="Type of transaction (operation)")
    status: TransactionStatus = Field(description="Current status")
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
    tx_type: str | None = Field(None, description="Filter by transaction type")
    status: TransactionStatus | None = Field(None, description="Filter by status")
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
# Error Response Schema
# ============================================================================


class TransactionErrorResponse(BaseModel):
    """Error response for transaction operations"""

    success: bool = Field(default=False)
    error: str = Field(description="Error message")
    error_code: str | None = Field(None, description="Error code")
    details: dict | None = Field(None, description="Additional error details")
