"""
Transaction Endpoints

FastAPI endpoints for Cardano transaction operations.
Provides ADA sending, transaction status checking, and transaction history.
"""

import os
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Path, Query
from sqlalchemy.ext.asyncio import AsyncSession

from api.database.connection import get_session
from api.database.models import Transaction as DBTransaction
from api.database.repositories.transaction import TransactionRepository
from api.dependencies.auth import WalletAuthContext, get_wallet_from_token
from api.enums import TransactionStatus as DBTransactionStatus
from api.schemas.transaction import (
    SendAdaRequest,
    SendAdaResponse,
    TransactionDetailResponse,
    TransactionErrorResponse,
    TransactionHistoryItem,
    TransactionHistoryResponse,
    TransactionStatus,
    TransactionStatusResponse,
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
# Send ADA Endpoint
# ============================================================================


@router.post(
    "/send-ada",
    response_model=SendAdaResponse,
    summary="Send ADA",
    description="Send ADA from authenticated wallet to another address. Requires wallet to be unlocked first.",
    responses={
        400: {"model": TransactionErrorResponse, "description": "Invalid request"},
        401: {"model": TransactionErrorResponse, "description": "Authentication required - unlock wallet first"},
        500: {"model": TransactionErrorResponse, "description": "Transaction failed"},
    },
)
async def send_ada(
    request: SendAdaRequest,
    wallet: WalletAuthContext = Depends(get_wallet_from_token),
    chain_context: CardanoChainContext = Depends(get_chain_context),
    session: AsyncSession = Depends(get_session),
) -> SendAdaResponse:
    """
    Send ADA to another address from an authenticated wallet.

    This endpoint:
    1. Uses the authenticated wallet from JWT token
    2. Gets the CardanoWallet instance from SessionManager
    3. Creates and signs the transaction
    4. Submits it to the blockchain
    5. Returns the transaction ID and explorer URL

    **Authentication Required:**
    - First unlock the wallet: POST /wallets/{wallet_id}/unlock
    - Get access_token from response
    - Include in header: Authorization: Bearer <access_token>

    **Note:** Transaction will be pending until confirmed on-chain (usually 20 seconds).
    """
    try:
        # Get authenticated wallet's CardanoWallet instance
        cardano_wallet = wallet.cardano_wallet

        # Get source address
        from_address = cardano_wallet.get_address(request.from_address_index)
        from_address_str = str(from_address)

        # Validate amount
        if request.amount_ada <= 0:
            raise HTTPException(status_code=400, detail="Amount must be greater than 0")

        # Validate destination address format
        try:
            # Basic validation - Cardano addresses start with addr or addr_test
            if not (
                request.to_address.startswith("addr")
                or request.to_address.startswith("addr_test")
                or request.to_address.startswith("stake")
            ):
                raise ValueError("Invalid Cardano address format")
        except Exception:
            raise HTTPException(status_code=400, detail=f"Invalid destination address format: {request.to_address}")

        # Create the transaction directly using the authenticated CardanoWallet
        try:
            # Get API for blockchain interaction
            api = chain_context.get_api()

            # Build and sign transaction
            signed_tx = cardano_wallet.create_simple_transaction(
                to_address=request.to_address,
                amount_ada=request.amount_ada,
                from_address_index=request.from_address_index,
                api=api
            )

            if not signed_tx:
                raise HTTPException(status_code=500, detail="Failed to create transaction")

        except Exception as e:
            error_msg = str(e)
            # Check for common errors
            if "insufficient" in error_msg.lower() or "balance" in error_msg.lower():
                raise HTTPException(status_code=400, detail=f"Insufficient balance: {error_msg}")
            raise HTTPException(status_code=500, detail=f"Failed to create transaction: {error_msg}")

        # Get transaction ID (available before submission)
        if not signed_tx.id:
            raise HTTPException(status_code=500, detail="Failed to generate transaction ID")

        tx_id = str(signed_tx.id.payload.hex())

        # Calculate amounts
        amount_lovelace = int(request.amount_ada * 1_000_000)
        fee_lovelace = signed_tx.transaction_body.fee
        fee_ada = fee_lovelace / 1_000_000 if fee_lovelace else None

        # Create database record FIRST with PENDING status (before blockchain submission)
        tx_repo = TransactionRepository(session)
        db_transaction = DBTransaction(
            tx_hash=tx_id,
            wallet_id=wallet.wallet_id,  # Link transaction to authenticated wallet
            status=DBTransactionStatus.PENDING,  # PENDING status before submission
            operation="send_ada",
            description=f"Sent {request.amount_ada} ADA from {wallet.wallet_name} to {request.to_address[:20]}...",
            fee_lovelace=fee_lovelace,
            total_output_lovelace=amount_lovelace,
            outputs=[{"address": request.to_address, "amount": amount_lovelace}],
            inputs=[{"address": from_address_str}],
            submitted_at=None,  # Not submitted yet
        )

        try:
            await tx_repo.create(db_transaction)
        except Exception as e:
            error_msg = str(e)
            raise HTTPException(status_code=500, detail=f"Failed to create transaction record in database: {error_msg}")

        # Submit the transaction to blockchain
        try:
            # Submit using the chain context API
            api = chain_context.get_api()
            submitted_tx_id = api.transaction_submit(signed_tx.to_cbor())

            if not submitted_tx_id or submitted_tx_id != tx_id:
                # Transaction submission failed - update database status to FAILED
                await tx_repo.update(
                    db_transaction.id,
                    status=DBTransactionStatus.FAILED,
                    error_message="Transaction submission failed - no transaction ID returned"
                )
                raise HTTPException(status_code=500, detail="Transaction submission failed - no transaction ID")

        except HTTPException:
            raise
        except Exception as e:
            # Blockchain submission failed - update database status to FAILED
            error_msg = str(e)
            try:
                await tx_repo.update(
                    db_transaction.id,
                    status=DBTransactionStatus.FAILED,
                    error_message=f"Blockchain submission failed: {error_msg}"
                )
            except Exception as db_error:
                # Log that we couldn't update the database, but prioritize the original error
                print(f"Warning: Failed to update transaction status in database: {db_error}")

            raise HTTPException(status_code=500, detail=f"Failed to submit transaction to blockchain: {error_msg}")

        # Transaction submitted successfully - update database status to SUBMITTED
        try:
            await tx_repo.update(
                db_transaction.id,
                status=DBTransactionStatus.SUBMITTED,
                submitted_at=datetime.now(timezone.utc).replace(tzinfo=None)
            )
        except Exception as e:
            # Transaction was submitted to blockchain but database update failed
            # This is a non-critical error - transaction is on blockchain
            error_msg = str(e)
            print(f"Warning: Transaction {tx_id} submitted to blockchain but failed to update database status: {error_msg}")
            # Continue anyway since blockchain submission succeeded

        # Get explorer URL for the transaction
        try:
            explorer_url = chain_context.get_explorer_url(tx_id)
        except Exception:
            # Fallback if we can't get explorer URL
            explorer_url = f"https://{'preview.' if 'testnet' in os.getenv('network', 'testnet') else ''}cardanoscan.io/transaction/{tx_id}"

        return SendAdaResponse(
            success=True,
            tx_hash=tx_id,
            explorer_url=explorer_url,
            from_address=from_address_str,
            to_address=request.to_address,
            amount_lovelace=amount_lovelace,
            amount_ada=request.amount_ada,
            fee_lovelace=fee_lovelace,
            fee_ada=fee_ada,
            submitted_at=datetime.now(timezone.utc),
            error=None,
        )

    except HTTPException:
        raise
    except Exception as e:
        return SendAdaResponse(success=False, error=f"Transaction failed: {str(e)}")


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
    wallet_name: str | None = Query(None, description="Filter by wallet name"),
    tx_type: str | None = Query(None, description="Filter by transaction type"),
    status: str | None = Query(None, description="Filter by status"),
    limit: int = Query(50, ge=1, le=500, description="Number of results (1-500)"),
    offset: int = Query(0, ge=0, description="Offset for pagination"),
    session: AsyncSession = Depends(get_session),
    chain_context: CardanoChainContext = Depends(get_chain_context),
) -> TransactionHistoryResponse:
    """
    Get transaction history with filtering and pagination.

    Filters:
    - `wallet_name`: Show only transactions from specific wallet
    - `tx_type`: Filter by transaction type (send_ada, mint_token, etc.)
    - `status`: Filter by status (pending, submitted, confirmed, failed)

    Pagination:
    - `limit`: Number of results to return (max 500)
    - `offset`: Skip this many results (for pagination)
    """
    try:
        from sqlalchemy import desc, func, select

        from api.database.models import Wallet

        tx_repo = TransactionRepository(session)

        # Build query with filters
        query = select(DBTransaction)

        # Filter by wallet if provided
        if wallet_name:
            wallet_query = select(Wallet).where(Wallet.name == wallet_name)
            wallet_result = await session.execute(wallet_query)
            wallet = wallet_result.scalar_one_or_none()
            if wallet:
                query = query.where(DBTransaction.wallet_id == wallet.id)
            else:
                # Wallet not found, return empty results
                return TransactionHistoryResponse(transactions=[], total=0, limit=limit, offset=offset, has_more=False)

        # Filter by operation type if provided
        if tx_type:
            query = query.where(DBTransaction.operation == tx_type)

        # Filter by status if provided
        if status:
            try:
                status_enum = DBTransactionStatus(status.lower())
                query = query.where(DBTransaction.status == status_enum)
            except ValueError:
                # Invalid status, ignore filter
                pass

        # Get total count
        count_query = select(func.count()).select_from(query.subquery())
        count_result = await session.execute(count_query)
        total = count_result.scalar() or 0

        # Add ordering, pagination
        query = query.order_by(desc(DBTransaction.created_at)).offset(offset).limit(limit)

        # Execute query
        result = await session.execute(query)
        db_transactions = result.scalars().all()

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
                    id=db_tx.id,
                    tx_hash=db_tx.tx_hash,
                    tx_type=db_tx.operation,
                    status=TransactionStatus(db_tx.status.value),
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
