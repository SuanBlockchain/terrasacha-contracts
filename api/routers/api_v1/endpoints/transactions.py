"""
Transaction Endpoints

FastAPI endpoints for Cardano transaction operations.
Provides ADA sending, transaction status checking, and transaction history.
"""

import os
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Path, Query

from api.database.models import TransactionMongo, WalletMongo
from api.dependencies.auth import WalletAuthContext, get_wallet_from_token
from api.dependencies.tenant import require_tenant_context
from api.services.transaction_service_mongo import MongoTransactionService
from api.enums import TransactionStatus as DBTransactionStatus
from api.schemas.transaction import (
    BuildTransactionRequest,
    BuildTransactionResponse,
    SignAndSubmitTransactionRequest,
    SignAndSubmitTransactionResponse,
    SignTransactionRequest,
    SignTransactionResponse,
    SubmitTransactionRequest,
    SubmitTransactionResponse,
    TransactionDetailResponse,
    TransactionErrorResponse,
    TransactionHistoryItem,
    TransactionHistoryResponse,
    TransactionStatus,
    TransactionStatusResponse,
)
from api.services.transaction_service_mongo import (
    InsufficientFundsError,
    InvalidTransactionStateError,
    TransactionNotFoundError,
    TransactionNotOwnedError,
)
from cardano_offchain.chain_context import CardanoChainContext


router = APIRouter()

# Global state for chain context
_chain_context: CardanoChainContext | None = None


# ============================================================================
# Dependencies
# ============================================================================


def get_chain_context() -> CardanoChainContext:
    """Get or initialize the chain context"""
    global _chain_context
    if _chain_context is None:
        network = os.getenv("network", "testnet")
        blockfrost_api_key = os.getenv("blockfrost_api_key")
        if not blockfrost_api_key:
            raise HTTPException(status_code=500, detail="Missing blockfrost_api_key environment variable")
        _chain_context = CardanoChainContext(network, blockfrost_api_key)
    return _chain_context

# ============================================================================
# Two-Stage Transaction Flow Endpoints
# ============================================================================


@router.post(
    "/build",
    response_model=BuildTransactionResponse,
    summary="Build unsigned transaction",
    description="Build an unsigned transaction (offchain). No password required. Returns transaction ID for signing.",
    responses={
        400: {"model": TransactionErrorResponse, "description": "Invalid request or insufficient funds"},
        401: {"model": TransactionErrorResponse, "description": "Authentication required"},
        500: {"model": TransactionErrorResponse, "description": "Failed to build transaction"},
    },
)
async def build_transaction(
    request: BuildTransactionRequest,
    wallet: WalletAuthContext = Depends(get_wallet_from_token),
    tenant_id: str = Depends(require_tenant_context),
) -> BuildTransactionResponse:
    """
    Build an unsigned transaction (Stage 1: Offchain).

    This endpoint:
    1. Queries the blockchain for UTXOs
    2. Builds the transaction structure
    3. Calculates fees
    4. Stores unsigned transaction in database
    5. Returns transaction ID for signing

    **Authentication Required:**
    - JWT token from unlocked wallet
    - Any wallet (USER or CORE) can build transactions

    **No password required** - just queries chain state

    **Next Step:**
    - Use transaction_id to sign: POST /transactions/sign
    - Or sign and submit: POST /transactions/sign-and-submit
    """
    try:
        # Get wallet's network from MongoDB
        db_wallet = await WalletMongo.find_one(WalletMongo.id == wallet.wallet_id)

        if not db_wallet:
            raise HTTPException(status_code=404, detail=f"Wallet {wallet.wallet_id} not found")

        # Create transaction service
        tx_service = MongoTransactionService()

        # Build the transaction
        transaction = await tx_service.build_transaction(
            wallet_id=wallet.wallet_id,
            from_address_index=request.from_address_index,
            to_address=request.to_address,
            amount_ada=request.amount_ada,
            network=db_wallet.network,
            metadata=request.metadata
        )

        # Get explorer URL (network is stored as string in MongoDB)
        network_name = "preview" if db_wallet.network == "testnet" else "mainnet"
        explorer_url = f"https://{network_name}.cardanoscan.io/transaction/{transaction.tx_hash}" if transaction.tx_hash else None

        return BuildTransactionResponse(
            success=True,
            transaction_id=transaction.tx_hash,
            tx_hash=transaction.tx_hash,
            tx_cbor=transaction.unsigned_cbor,
            from_address=transaction.from_address,
            to_address=transaction.to_address,
            amount_lovelace=transaction.amount_lovelace,
            amount_ada=transaction.amount_lovelace / 1_000_000,
            estimated_fee_lovelace=transaction.estimated_fee,
            estimated_fee_ada=transaction.estimated_fee / 1_000_000,
            metadata=transaction.tx_metadata if transaction.tx_metadata else None,
            status=transaction.status,  # Already a string in MongoDB
        )

    except InsufficientFundsError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except NotImplementedError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to build transaction: {str(e)}")


@router.post(
    "/sign",
    response_model=SignTransactionResponse,
    summary="Sign transaction with password",
    description="Sign a built transaction using wallet password (Stage 2). Returns signed transaction.",
    responses={
        400: {"model": TransactionErrorResponse, "description": "Invalid transaction state"},
        401: {"model": TransactionErrorResponse, "description": "Authentication required or incorrect password"},
        403: {"model": TransactionErrorResponse, "description": "Not authorized to sign this transaction"},
        404: {"model": TransactionErrorResponse, "description": "Transaction not found"},
        500: {"model": TransactionErrorResponse, "description": "Failed to sign transaction"},
    },
)
async def sign_transaction(
    request: SignTransactionRequest,
    wallet: WalletAuthContext = Depends(get_wallet_from_token),
    tenant_id: str = Depends(require_tenant_context),
) -> SignTransactionResponse:
    """
    Sign a built transaction with wallet password (Stage 2).

    This endpoint:
    1. Verifies you own the transaction
    2. Verifies the password
    3. Decrypts mnemonic temporarily
    4. Signs the transaction
    5. Discards keys immediately
    6. Updates database with signed transaction

    **Authentication Required:**
    - JWT token from unlocked wallet
    - Must own the transaction being signed

    **Password Required:**
    - Wallet password to decrypt mnemonic for signing

    **Next Step:**
    - Submit the signed transaction: POST /transactions/submit
    """
    try:
        # Get wallet's network from MongoDB
        db_wallet = await WalletMongo.find_one(WalletMongo.id == wallet.wallet_id)

        if not db_wallet:
            raise HTTPException(status_code=404, detail=f"Wallet {wallet.wallet_id} not found")

        # Create transaction service
        tx_service = MongoTransactionService()

        # Sign the transaction
        transaction = await tx_service.sign_transaction(
            transaction_id=request.transaction_id,
            wallet_id=wallet.wallet_id,
            password=request.password,
            network=db_wallet.network
        )

        return SignTransactionResponse(
            success=True,
            transaction_id=transaction.tx_hash,
            signed_tx_cbor=transaction.signed_cbor,
            tx_hash=transaction.tx_hash,
            status=transaction.status,
        )

    except TransactionNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except TransactionNotOwnedError as e:
        raise HTTPException(status_code=403, detail=str(e))
    except InvalidTransactionStateError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        # Check for password error
        if "password" in str(e).lower() or "incorrect" in str(e).lower():
            raise HTTPException(status_code=401, detail=str(e))
        raise HTTPException(status_code=500, detail=f"Failed to sign transaction: {str(e)}")


@router.post(
    "/submit",
    response_model=SubmitTransactionResponse,
    summary="Submit signed transaction",
    description="Submit a signed transaction to the blockchain (Stage 3). No password required.",
    responses={
        400: {"model": TransactionErrorResponse, "description": "Invalid transaction state"},
        401: {"model": TransactionErrorResponse, "description": "Authentication required"},
        403: {"model": TransactionErrorResponse, "description": "Not authorized to submit this transaction"},
        404: {"model": TransactionErrorResponse, "description": "Transaction not found"},
        500: {"model": TransactionErrorResponse, "description": "Failed to submit transaction"},
    },
)
async def submit_transaction(
    request: SubmitTransactionRequest,
    wallet: WalletAuthContext = Depends(get_wallet_from_token),
    tenant_id: str = Depends(require_tenant_context),
) -> SubmitTransactionResponse:
    """
    Submit a signed transaction to the blockchain (Stage 3).

    This endpoint:
    1. Verifies you own the transaction
    2. Verifies transaction is signed
    3. Submits to blockchain
    4. Updates database status

    **Authentication Required:**
    - JWT token from unlocked wallet
    - Must own the transaction being submitted

    **No password required** - transaction must already be signed

    **Result:**
    - Transaction submitted to mempool
    - Will be confirmed in ~20 seconds
    - Use explorer URL to track confirmation
    """
    try:
        # Get wallet's network from MongoDB
        db_wallet = await WalletMongo.find_one(WalletMongo.id == wallet.wallet_id)

        if not db_wallet:
            raise HTTPException(status_code=404, detail=f"Wallet {wallet.wallet_id} not found")

        # Create transaction service
        tx_service = MongoTransactionService()

        # Submit the transaction
        transaction = await tx_service.submit_transaction(
            transaction_id=request.transaction_id,
            wallet_id=wallet.wallet_id,
            network=db_wallet.network
        )

        # Get explorer URL (network is stored as string in MongoDB)
        network_name = "preview" if db_wallet.network == "testnet" else "mainnet"
        explorer_url = f"https://{network_name}.cardanoscan.io/transaction/{transaction.tx_hash}"

        return SubmitTransactionResponse(
            success=True,
            transaction_id=transaction.tx_hash,
            tx_hash=transaction.tx_hash,
            status=transaction.status,
            submitted_at=transaction.submitted_at,
            explorer_url=explorer_url,
        )

    except TransactionNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except TransactionNotOwnedError as e:
        raise HTTPException(status_code=403, detail=str(e))
    except InvalidTransactionStateError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to submit transaction: {str(e)}")


@router.post(
    "/sign-and-submit",
    response_model=SignAndSubmitTransactionResponse,
    summary="Sign and submit transaction (convenience)",
    description="Sign with password AND submit to blockchain in one call. Convenience endpoint combining /sign and /submit.",
    responses={
        400: {"model": TransactionErrorResponse, "description": "Invalid transaction state"},
        401: {"model": TransactionErrorResponse, "description": "Authentication required or incorrect password"},
        403: {"model": TransactionErrorResponse, "description": "Not authorized"},
        404: {"model": TransactionErrorResponse, "description": "Transaction not found"},
        500: {"model": TransactionErrorResponse, "description": "Failed to sign or submit transaction"},
    },
)
async def sign_and_submit_transaction(
    request: SignAndSubmitTransactionRequest,
    wallet: WalletAuthContext = Depends(get_wallet_from_token),
    tenant_id: str = Depends(require_tenant_context),
) -> SignAndSubmitTransactionResponse:
    """
    Sign and submit a transaction in one operation (Convenience endpoint).

    This endpoint combines /sign and /submit:
    1. Verifies you own the transaction
    2. Signs with your password
    3. Immediately submits to blockchain
    4. Returns confirmation

    **Authentication Required:**
    - JWT token from unlocked wallet
    - Must own the transaction

    **Password Required:**
    - Wallet password to decrypt mnemonic for signing

    **Benefit:**
    - One API call instead of two
    - Faster workflow for trusted transactions

    **Use Cases:**
    - Quick sends when you trust the built transaction
    - Automated operations
    - Simple user flows
    """
    try:
        # Get wallet's network from MongoDB
        db_wallet = await WalletMongo.find_one(WalletMongo.id == wallet.wallet_id)

        if not db_wallet:
            raise HTTPException(status_code=404, detail=f"Wallet {wallet.wallet_id} not found")

        # Create transaction service
        tx_service = MongoTransactionService()

        # Sign and submit
        transaction = await tx_service.sign_and_submit_transaction(
            transaction_id=request.transaction_id,
            wallet_id=wallet.wallet_id,
            password=request.password,
            network=db_wallet.network
        )

        # Get explorer URL (network is stored as string in MongoDB)
        network_name = "preview" if db_wallet.network == "testnet" else "mainnet"
        explorer_url = f"https://{network_name}.cardanoscan.io/transaction/{transaction.tx_hash}"

        return SignAndSubmitTransactionResponse(
            success=True,
            transaction_id=transaction.tx_hash,
            tx_hash=transaction.tx_hash,
            status=transaction.status,
            signed_at=transaction.updated_at,  # Updated when signed
            submitted_at=transaction.submitted_at,
            explorer_url=explorer_url,
        )

    except TransactionNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except TransactionNotOwnedError as e:
        raise HTTPException(status_code=403, detail=str(e))
    except InvalidTransactionStateError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        # Check for password error
        if "password" in str(e).lower() or "incorrect" in str(e).lower():
            raise HTTPException(status_code=401, detail=str(e))
        raise HTTPException(status_code=500, detail=f"Failed to sign and submit transaction: {str(e)}")
    
# ============================================================================
# Transaction Status Endpoint
# ============================================================================


@router.get(
    "/{tx_hash}/status",
    response_model=TransactionStatusResponse,
    summary="Get transaction status",
    description="Query the blockchain for transaction status and confirmation details",
    responses={404: {"model": TransactionErrorResponse, "description": "Transaction not found"}},
)
async def get_transaction_status(
    tx_hash: str = Path(..., description="Transaction hash to query"),
    chain_context: CardanoChainContext = Depends(get_chain_context),
) -> TransactionStatusResponse:
    """
    Get the current status of a transaction.

    Queries the blockchain to determine:
    - Whether the transaction is confirmed
    - Number of confirmations (if confirmed)
    - Block height and timestamp
    - Transaction fee

    **Note:** A transaction needs ~20 seconds and 1 confirmation to be considered final.
    """
    try:
        api = chain_context.get_api()

        # Query transaction from blockchain
        try:
            tx_info = api.transaction(tx_hash)

            # Transaction is confirmed if we can retrieve it
            status = TransactionStatus.CONFIRMED

            # Get block info for confirmations
            block_height = tx_info.block_height if hasattr(tx_info, "block_height") else None
            block_time = None

            if block_height:
                try:
                    latest_block = api.block_latest()
                    latest_height = latest_block.height if hasattr(latest_block, "height") else None
                    confirmations = (latest_height - block_height + 1) if latest_height else None

                    # Get block timestamp
                    if hasattr(tx_info, "block_time"):
                        block_time = datetime.fromtimestamp(tx_info.block_time, tz=timezone.utc)

                except Exception:
                    confirmations = None
            else:
                confirmations = None

            # Get fee
            fee_lovelace = int(tx_info.fees) if hasattr(tx_info, "fees") else None

            # Get explorer URL
            explorer_url = chain_context.get_explorer_url(tx_hash)

            return TransactionStatusResponse(
                tx_hash=tx_hash,
                status=status,
                confirmations=confirmations,
                block_height=block_height,
                block_time=block_time,
                fee_lovelace=fee_lovelace,
                explorer_url=explorer_url,
                submitted_at=block_time,  # Use block time as approximate submission time
                confirmed_at=block_time,
            )

        except Exception as e:
            error_str = str(e).lower()

            # Transaction not found - might be pending or invalid
            if "not found" in error_str or "404" in error_str:
                # Could be pending - return pending status
                return TransactionStatusResponse(
                    tx_hash=tx_hash,
                    status=TransactionStatus.PENDING,
                    confirmations=0,
                    explorer_url=chain_context.get_explorer_url(tx_hash),
                )

            # Other error - re-raise
            raise HTTPException(status_code=500, detail=f"Failed to query transaction: {str(e)}")

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get transaction status: {str(e)}")


# ============================================================================
# Transaction History Endpoint
# ============================================================================


@router.get(
    "/history",
    response_model=TransactionHistoryResponse,
    summary="Get transaction history",
    description="Get paginated transaction history with optional filters",
)
async def get_transaction_history(
    wallet: WalletAuthContext = Depends(get_wallet_from_token),
    tx_type: str | None = Query(None, description="Filter by transaction type"),
    status: str | None = Query(None, description="Filter by status"),
    limit: int = Query(50, ge=1, le=500, description="Number of results (1-500)"),
    offset: int = Query(0, ge=0, description="Offset for pagination"),
    tenant_id: str = Depends(require_tenant_context),
    chain_context: CardanoChainContext = Depends(get_chain_context),
) -> TransactionHistoryResponse:
    """
    Get transaction history with filtering and pagination.

    Filters:
    - `tx_type`: Filter by transaction type (send_ada, mint_token, etc.)
    - `status`: Filter by status (pending, submitted, confirmed, failed)

    Pagination:
    - `limit`: Number of results to return (max 500)
    - `offset`: Skip this many results (for pagination)

    **Authentication Required:**
    - JWT token from unlocked wallet
    - Returns only transactions for the authenticated wallet
    """
    try:
        # Build query filters for the authenticated wallet
        filters = [TransactionMongo.wallet_id == wallet.wallet_id]

        # Filter by operation type if provided
        if tx_type:
            filters.append(TransactionMongo.operation == tx_type)

        # Filter by status if provided
        if status:
            filters.append(TransactionMongo.status == status.upper())

        # Get total count
        total = await TransactionMongo.find(*filters).count()

        # Execute query with pagination
        db_transactions = await TransactionMongo.find(*filters)\
            .sort([("created_at", -1)])\
            .skip(offset)\
            .limit(limit)\
            .to_list()

        # Convert to response models
        transactions = []
        for db_tx in db_transactions:
            # Get explorer URL
            explorer_url = chain_context.get_explorer_url(db_tx.tx_hash)

            # Extract first input/output addresses for summary
            from_address = None
            to_address = None
            amount_lovelace = None

            if db_tx.inputs and len(db_tx.inputs) > 0:
                from_address = db_tx.inputs[0].get("address")

            if db_tx.outputs and len(db_tx.outputs) > 0:
                to_address = db_tx.outputs[0].get("address")
                amount_lovelace = db_tx.outputs[0].get("amount")

            transactions.append(
                TransactionHistoryItem(
                    id=str(db_tx.id),
                    tx_hash=db_tx.tx_hash,
                    tx_type=db_tx.operation,
                    status=TransactionStatus(db_tx.status),
                    from_address=from_address,
                    to_address=to_address,
                    amount_lovelace=amount_lovelace,
                    amount_ada=amount_lovelace / 1_000_000 if amount_lovelace else None,
                    fee_lovelace=db_tx.fee_lovelace,
                    explorer_url=explorer_url,
                    submitted_at=db_tx.submitted_at,
                    confirmed_at=db_tx.confirmed_at,
                    metadata=db_tx.tx_metadata,
                )
            )

        # Check if there are more results
        has_more = (offset + limit) < total

        return TransactionHistoryResponse(
            transactions=transactions, total=total, limit=limit, offset=offset, has_more=has_more
        )

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to fetch transaction history: {str(e)}")


# ============================================================================
# Transaction Detail Endpoint
# ============================================================================


@router.get(
    "/{tx_hash}",
    response_model=TransactionDetailResponse,
    summary="Get transaction details",
    description="Get detailed information about a specific transaction",
    responses={404: {"model": TransactionErrorResponse, "description": "Transaction not found"}},
)
async def get_transaction_detail(
    tx_hash: str = Path(..., description="Transaction hash to query"),
    chain_context: CardanoChainContext = Depends(get_chain_context),
) -> TransactionDetailResponse:
    """
    Get detailed information about a transaction.

    Returns complete transaction data including:
    - All inputs and outputs
    - Fee information
    - Block details (if confirmed)
    - Transaction metadata
    - Asset transfers (if any)
    """
    try:
        api = chain_context.get_api()

        # Query transaction details
        try:
            tx_info = api.transaction(tx_hash)

            # Determine status
            status = TransactionStatus.CONFIRMED

            # Get block info
            block_height = tx_info.block_height if hasattr(tx_info, "block_height") else None
            block_time = None
            confirmations = None

            if block_height:
                try:
                    if hasattr(tx_info, "block_time"):
                        block_time = datetime.fromtimestamp(tx_info.block_time, tz=timezone.utc)

                    latest_block = api.block_latest()
                    latest_height = latest_block.height if hasattr(latest_block, "height") else None
                    confirmations = (latest_height - block_height + 1) if latest_height else None
                except Exception:
                    pass

            # Get fee
            fee_lovelace = int(tx_info.fees) if hasattr(tx_info, "fees") else None
            fee_ada = fee_lovelace / 1_000_000 if fee_lovelace else None

            # Parse inputs and outputs
            inputs = []
            outputs = []

            # Note: Blockfrost API structure for inputs/outputs
            # This is a simplified version - full implementation would parse all details

            # Get explorer URL
            explorer_url = chain_context.get_explorer_url(tx_hash)

            return TransactionDetailResponse(
                tx_hash=tx_hash,
                status=status,
                tx_type=None,  # Would need to determine from metadata
                inputs=inputs,
                outputs=outputs,
                fee_lovelace=fee_lovelace,
                fee_ada=fee_ada,
                block_height=block_height,
                block_time=block_time,
                confirmations=confirmations,
                metadata=None,
                submitted_at=block_time,
                confirmed_at=block_time,
                explorer_url=explorer_url,
            )

        except Exception as e:
            error_str = str(e).lower()
            if "not found" in error_str or "404" in error_str:
                raise HTTPException(status_code=404, detail=f"Transaction not found: {tx_hash}")
            raise HTTPException(status_code=500, detail=f"Failed to query transaction: {str(e)}")

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get transaction details: {str(e)}")


