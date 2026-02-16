"""
Transaction Endpoints

FastAPI endpoints for Cardano transaction operations.
Provides ADA sending, transaction status checking, and transaction history.
"""

import logging
import os
import traceback
from datetime import datetime, timezone

logger = logging.getLogger(__name__)

import pycardano as pc
from blockfrost import ApiError
from fastapi import APIRouter, Depends, HTTPException, Path, Query

from api.database.models import TransactionMongo, WalletMongo
from api.dependencies.auth import WalletAuthContext, get_wallet_from_token, require_core_wallet
from api.dependencies.tenant import require_tenant_context, get_tenant_database
from api.services.transaction_service_mongo import MongoTransactionService
from api.enums import TransactionStatus as DBTransactionStatus
from api.schemas.contract import (
    ConfirmReferenceScriptRequest,
    ConfirmReferenceScriptResponse,
    ContractErrorResponse,
    DeployReferenceScriptRequest,
    DeployReferenceScriptResponse,
)
from api.schemas.transaction import (
    AddressDestin,
    BlockchainTransactionHistoryResponse,
    BlockchainTransactionItem,
    BlockchainTransactionInput,
    BlockchainTransactionOutput,
    BuildTransactionRequest,
    BuildTransactionResponse,
    MinLovelaceResponse,
    MultiAssetItem,
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
from api.enums import TransactionType
from api.services.contract_service_mongo import (
    MongoContractService,
    ContractCompilationError,
    ContractNotFoundError,
    InvalidContractParametersError,
)
from api.services.transaction_service_mongo import (
    InsufficientFundsError,
    InvalidTransactionStateError,
    TransactionNotFoundError,
    TransactionNotOwnedError,
    _prepare_tx_dict_for_validation,
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
    tenant_db = Depends(get_tenant_database),
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
        # Get wallet's network from tenant database
        from api.services.wallet_service_mongo import MongoWalletService
        wallet_service = MongoWalletService(database=tenant_db)
        db_wallet = await wallet_service.get_wallet(wallet.wallet_id)

        if not db_wallet:
            raise HTTPException(status_code=404, detail=f"Wallet {wallet.wallet_id} not found")

        # Create transaction service with tenant database
        tx_service = MongoTransactionService(database=tenant_db)

        # Convert assets to dicts for the service layer
        assets_dicts = [item.model_dump() for item in request.assets] if request.assets else None

        # Build the transaction
        transaction = await tx_service.build_transaction(
            wallet_id=wallet.wallet_id,
            to_address=request.to_address,
            amount_ada=request.amount_ada,
            network=db_wallet.network,
            metadata=request.metadata,
            assets=assets_dicts
        )

        # Get explorer URL (network is stored as string in MongoDB)
        network_name = "preview" if db_wallet.network == "testnet" else "mainnet"
        explorer_url = f"https://{network_name}.cardanoscan.io/transaction/{transaction.tx_hash}" if transaction.tx_hash else None

        # Transform inputs to new format (handle legacy format without amount/output_index)
        detailed_inputs = []
        total_input_lovelace = 0
        for inp in (transaction.inputs or []):
            if "amount" in inp and "output_index" in inp:
                # New format - use as-is
                detailed_inputs.append(BlockchainTransactionInput(**inp))
                for a in inp.get("amount", []):
                    if a.get("unit") == "lovelace":
                        total_input_lovelace += int(a["quantity"])
            else:
                # Legacy format - skip detailed input (not enough data)
                pass

        # Transform outputs to new format (handle legacy format without amount list/output_index)
        detailed_outputs = []
        total_output_lovelace = 0
        for out in (transaction.outputs or []):
            if "amount" in out and isinstance(out.get("amount"), list) and "output_index" in out:
                # New format - use as-is
                detailed_outputs.append(BlockchainTransactionOutput(**out))
                for a in out.get("amount", []):
                    if a.get("unit") == "lovelace":
                        total_output_lovelace += int(a["quantity"])
            else:
                # Legacy format - skip detailed output (not enough data)
                pass

        # Use stored total_output_lovelace if available, otherwise use calculated
        final_total_output = transaction.total_output_lovelace or total_output_lovelace

        # Calculate transaction size from CBOR if available
        tx_size = len(bytes.fromhex(transaction.unsigned_cbor)) if transaction.unsigned_cbor else None

        # Get actual fee (fee_lovelace if available, otherwise estimated_fee)
        actual_fee = transaction.fee_lovelace or transaction.estimated_fee

        # Reconstruct assets from stored data for response
        response_assets = None
        min_lovelace_calculated = None
        if transaction.assets_sent:
            response_assets = [MultiAssetItem(**a) for a in transaction.assets_sent]
            # Re-derive min_lovelace from the stored amount and request
            # If the operation is send_tokens, the amount_lovelace includes min_lovelace consideration
            if transaction.operation == "send_tokens":
                # Calculate what min_lovelace was (for informational purposes)
                try:
                    from api.services.transaction_service_mongo import _build_multi_asset_from_items
                    ma = _build_multi_asset_from_items(transaction.assets_sent)
                    test_out = pc.TransactionOutput(
                        pc.Address.from_primitive(transaction.to_address),
                        pc.Value(0, ma)
                    )
                    cc = get_chain_context()
                    ctx = cc.get_context()
                    min_lovelace_calculated = pc.min_lovelace(ctx, output=test_out)
                except Exception:
                    # Non-critical: min_lovelace is informational
                    pass

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
            assets=response_assets,
            min_lovelace_calculated=min_lovelace_calculated,
            metadata=transaction.tx_metadata if transaction.tx_metadata else None,
            status=transaction.status,  # Already a string in MongoDB
            # Detailed transaction information (empty if legacy format)
            inputs=detailed_inputs,
            outputs=detailed_outputs,
            fee_lovelace=actual_fee,
            fee_ada=actual_fee / 1_000_000,
            tx_size=tx_size,
            total_input_lovelace=total_input_lovelace,
            total_output_lovelace=final_total_output,
        )

    except InsufficientFundsError as e:
        logger.warning(f"Insufficient funds for wallet {wallet.wallet_id}: {e}")
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        # Log full exception details for debugging
        error_type = type(e).__name__
        error_msg = str(e) if str(e) else "No error message"
        logger.error(
            f"Failed to build transaction for wallet {wallet.wallet_id}: "
            f"[{error_type}] {error_msg}\n"
            f"Traceback:\n{traceback.format_exc()}"
        )
        raise HTTPException(
            status_code=500,
            detail=f"Failed to build transaction ({error_type}): {error_msg}"
        )


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
    tenant_db = Depends(get_tenant_database),
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
        # Get wallet's network from tenant database
        from api.services.wallet_service_mongo import MongoWalletService
        wallet_service = MongoWalletService(database=tenant_db)
        db_wallet = await wallet_service.get_wallet(wallet.wallet_id)

        if not db_wallet:
            raise HTTPException(status_code=404, detail=f"Wallet {wallet.wallet_id} not found")

        # Create transaction service with tenant database
        tx_service = MongoTransactionService(database=tenant_db)

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
        logger.warning(f"Transaction not found: {request.transaction_id}")
        raise HTTPException(status_code=404, detail=str(e))
    except TransactionNotOwnedError as e:
        logger.warning(f"Transaction not owned by wallet {wallet.wallet_id}: {request.transaction_id}")
        raise HTTPException(status_code=403, detail=str(e))
    except InvalidTransactionStateError as e:
        logger.warning(f"Invalid transaction state for {request.transaction_id}: {e}")
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        # Check for password error
        if "password" in str(e).lower() or "incorrect" in str(e).lower():
            logger.warning(f"Password error for wallet {wallet.wallet_id}")
            raise HTTPException(status_code=401, detail=str(e))
        error_type = type(e).__name__
        error_msg = str(e) if str(e) else "No error message"
        logger.error(
            f"Failed to sign transaction {request.transaction_id}: "
            f"[{error_type}] {error_msg}\n"
            f"Traceback:\n{traceback.format_exc()}"
        )
        raise HTTPException(
            status_code=500,
            detail=f"Failed to sign transaction ({error_type}): {error_msg}"
        )


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
    tenant_db = Depends(get_tenant_database),
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
        # Get wallet's network from tenant database
        from api.services.wallet_service_mongo import MongoWalletService
        wallet_service = MongoWalletService(database=tenant_db)
        db_wallet = await wallet_service.get_wallet(wallet.wallet_id)

        if not db_wallet:
            raise HTTPException(status_code=404, detail=f"Wallet {wallet.wallet_id} not found")

        # Create transaction service with tenant database
        tx_service = MongoTransactionService(database=tenant_db)

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
        logger.warning(f"Transaction not found for submit: {request.transaction_id}")
        raise HTTPException(status_code=404, detail=str(e))
    except TransactionNotOwnedError as e:
        logger.warning(f"Transaction not owned by wallet {wallet.wallet_id} for submit: {request.transaction_id}")
        raise HTTPException(status_code=403, detail=str(e))
    except InvalidTransactionStateError as e:
        logger.warning(f"Invalid transaction state for submit {request.transaction_id}: {e}")
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        error_type = type(e).__name__
        error_msg = str(e) if str(e) else "No error message"
        logger.error(
            f"Failed to submit transaction {request.transaction_id}: "
            f"[{error_type}] {error_msg}\n"
            f"Traceback:\n{traceback.format_exc()}"
        )
        raise HTTPException(
            status_code=500,
            detail=f"Failed to submit transaction ({error_type}): {error_msg}"
        )


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
    tenant_db = Depends(get_tenant_database),
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
        # Get wallet's network from tenant database
        from api.services.wallet_service_mongo import MongoWalletService
        wallet_service = MongoWalletService(database=tenant_db)
        db_wallet = await wallet_service.get_wallet(wallet.wallet_id)

        if not db_wallet:
            raise HTTPException(status_code=404, detail=f"Wallet {wallet.wallet_id} not found")

        # Create transaction service with tenant database
        tx_service = MongoTransactionService(database=tenant_db)

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
        logger.warning(f"Transaction not found for sign-and-submit: {request.transaction_id}")
        raise HTTPException(status_code=404, detail=str(e))
    except TransactionNotOwnedError as e:
        logger.warning(f"Transaction not owned by wallet {wallet.wallet_id} for sign-and-submit: {request.transaction_id}")
        raise HTTPException(status_code=403, detail=str(e))
    except InvalidTransactionStateError as e:
        logger.warning(f"Invalid transaction state for sign-and-submit {request.transaction_id}: {e}")
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        # Check for password error
        if "password" in str(e).lower() or "incorrect" in str(e).lower():
            logger.warning(f"Password error for sign-and-submit wallet {wallet.wallet_id}")
            raise HTTPException(status_code=401, detail=str(e))
        error_type = type(e).__name__
        error_msg = str(e) if str(e) else "No error message"
        logger.error(
            f"Failed to sign-and-submit transaction {request.transaction_id}: "
            f"[{error_type}] {error_msg}\n"
            f"Traceback:\n{traceback.format_exc()}"
        )
        raise HTTPException(
            status_code=500,
            detail=f"Failed to sign and submit transaction ({error_type}): {error_msg}"
        )


# ============================================================================
# Reference Script Deployment Endpoints
# ============================================================================


@router.post(
    "/deploy-reference-script",
    response_model=DeployReferenceScriptResponse,
    summary="Deploy contract as reference script (CORE only)",
    description="Build an unsigned transaction to deploy a compiled contract as an on-chain reference script. Requires CORE wallet.",
    responses={
        400: {"model": ContractErrorResponse, "description": "Invalid request, already deployed, or insufficient funds"},
        403: {"model": ContractErrorResponse, "description": "CORE wallet required"},
        404: {"model": ContractErrorResponse, "description": "Contract or wallet not found"},
        500: {"model": ContractErrorResponse, "description": "Transaction building failed"},
    },
)
async def deploy_reference_script(
    request: DeployReferenceScriptRequest,
    core_wallet: WalletAuthContext = Depends(require_core_wallet),
    tenant_db=Depends(get_tenant_database),
    chain_context: CardanoChainContext = Depends(get_chain_context),
) -> DeployReferenceScriptResponse:
    """
    Build an unsigned transaction to deploy a contract as an on-chain reference script.

    Reference scripts allow transactions to reference the script on-chain instead of
    including it in every transaction, significantly reducing transaction fees.

    **No password required** — only builds the unsigned transaction.

    **Flow:**
    1. `POST /transactions/deploy-reference-script` (this endpoint) -> get `transaction_id`
    2. `POST /transactions/sign` with `transaction_id` + password
    3. `POST /transactions/submit` with `transaction_id`
    4. `POST /transactions/confirm-reference-script` with `transaction_id`
    """
    try:
        wallet_id = request.wallet_id or core_wallet.wallet_id

        wallet_collection = tenant_db.get_collection("wallets")
        wallet_dict = await wallet_collection.find_one({"_id": wallet_id})

        if not wallet_dict:
            raise HTTPException(status_code=404, detail=f"Wallet {wallet_id} not found")

        wallet_dict["id"] = wallet_dict.pop("_id")
        db_wallet = WalletMongo.model_validate(wallet_dict)

        contract_service = MongoContractService(database=tenant_db)
        result = await contract_service.build_deploy_reference_script_transaction(
            wallet_address=db_wallet.enterprise_address,
            network=db_wallet.network,
            wallet_id=wallet_id,
            chain_context=chain_context,
            policy_id=request.policy_id,
            destination_address=request.destination_address,
        )

        return DeployReferenceScriptResponse(
            success=result["success"],
            transaction_id=result["transaction_id"],
            tx_cbor=result["tx_cbor"],
            contract_policy_id=result["contract_policy_id"],
            contract_name=result["contract_name"],
            destination_address=result["destination_address"],
            min_lovelace=result["min_lovelace"],
            reference_output_index=result["reference_output_index"],
            fee_lovelace=result["fee_lovelace"],
            inputs=result["inputs"],
            outputs=result["outputs"],
        )

    except ContractNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except InvalidContractParametersError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except ContractCompilationError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to build reference script transaction: {str(e)}")


@router.post(
    "/confirm-reference-script",
    response_model=ConfirmReferenceScriptResponse,
    summary="Confirm reference script deployment (CORE only)",
    description="Confirm that a reference script deployment transaction has been submitted, updating the contract record. Requires CORE wallet.",
    responses={
        400: {"model": ContractErrorResponse, "description": "Transaction not submitted or invalid operation"},
        403: {"model": ContractErrorResponse, "description": "CORE wallet required"},
        404: {"model": ContractErrorResponse, "description": "Transaction or contract not found"},
        500: {"model": ContractErrorResponse, "description": "Confirmation failed"},
    },
)
async def confirm_reference_script(
    request: ConfirmReferenceScriptRequest,
    _core_wallet: WalletAuthContext = Depends(require_core_wallet),
    tenant_db=Depends(get_tenant_database),
) -> ConfirmReferenceScriptResponse:
    """
    Confirm reference script deployment after transaction submission.

    After deploying a reference script (deploy → sign → submit), this endpoint
    updates the contract record with the on-chain reference UTXO information.

    **Prerequisites:**
    - The deploy-reference-script transaction must be in SUBMITTED or CONFIRMED state

    **What it does:**
    - Updates the contract's `reference_utxo`, `reference_tx_hash`, and `storage_type`
    - The contract can then be referenced in future transactions instead of being included inline

    **Flow:**
    1. `POST /transactions/deploy-reference-script` -> get `transaction_id`
    2. `POST /transactions/sign` + `POST /transactions/submit`
    3. `POST /transactions/confirm-reference-script` (this endpoint)
    """
    try:
        contract_service = MongoContractService(database=tenant_db)
        result = await contract_service.confirm_reference_script_deployment(
            transaction_id=request.transaction_id,
        )

        return ConfirmReferenceScriptResponse(
            success=result["success"],
            message=result["message"],
            policy_id=result["policy_id"],
            contract_name=result["contract_name"],
            reference_utxo=result["reference_utxo"],
            reference_tx_hash=result["reference_tx_hash"],
        )

    except ContractNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except InvalidContractParametersError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except ContractCompilationError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to confirm reference script deployment: {str(e)}")


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
    _tenant: str = Depends(require_tenant_context),
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
    wallet_id: str | None = Query(
        None,
        description="Filter by wallet ID (payment key hash). If not provided, returns all transactions for the tenant."
    ),
    tx_type: TransactionType | None = Query(
        None,
        description="Filter by transaction type (send_ada, mint_token, mint_protocol, burn_token, stake, unstake, smart_contract)"
    ),
    status: TransactionStatus | None = Query(
        None,
        description="Filter by status (BUILT, SIGNED, PENDING, SUBMITTED, CONFIRMED, FAILED)"
    ),
    limit: int = Query(50, ge=1, le=500, description="Number of results (1-500)"),
    offset: int = Query(0, ge=0, description="Offset for pagination"),
    tenant_db = Depends(get_tenant_database),
    chain_context: CardanoChainContext = Depends(get_chain_context),
) -> TransactionHistoryResponse:
    """
    Get transaction history with filtering and pagination.

    **Filters:**
    - `wallet_id`: Filter by wallet ID (payment key hash). Optional - if not provided,
      returns all transactions for the tenant.

    - `tx_type`: Transaction type
      - `send_ada` - Simple ADA transfer
      - `mint_token` - Mint new tokens
      - `mint_protocol` - Mint protocol-specific tokens
      - `burn_token` - Burn/destroy tokens
      - `stake` - Stake ADA
      - `unstake` - Withdraw staked ADA
      - `smart_contract` - Smart contract operation

    - `status`: Transaction status
      - `BUILT` - Transaction built (unsigned)
      - `SIGNED` - Transaction signed
      - `PENDING` - Created but not submitted
      - `SUBMITTED` - Submitted to blockchain
      - `CONFIRMED` - Confirmed on-chain
      - `FAILED` - Transaction failed

    **Pagination:**
    - `limit`: Number of results to return (max 500)
    - `offset`: Skip this many results (for pagination)

    **Authentication Required:**
    - API key header (X-API-Key)
    - Returns transactions for the tenant
    """
    try:
        # Get transaction collection from tenant database
        collection = tenant_db.get_collection("transactions")

        # Build query filters (wallet_id is optional)
        query_filter = {}
        if wallet_id:
            query_filter["wallet_id"] = wallet_id

        # Filter by operation type if provided
        if tx_type:
            query_filter["operation"] = tx_type.value

        # Filter by status if provided
        if status:
            query_filter["status"] = status.value

        # Get total count
        total = await collection.count_documents(query_filter)

        # Execute query with pagination
        cursor = collection.find(query_filter)\
            .sort("created_at", -1)\
            .skip(offset)\
            .limit(limit)

        db_transactions_dicts = await cursor.to_list(length=limit)

        # Convert to TransactionMongo models
        db_transactions = []
        for tx_dict in db_transactions_dicts:
            tx_dict = _prepare_tx_dict_for_validation(tx_dict)
            db_transactions.append(TransactionMongo.model_validate(tx_dict))

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
    _tenant: str = Depends(require_tenant_context),
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


# ============================================================================
# Min Lovelace Calculation Endpoint
# ============================================================================


@router.post(
    "/min-lovelace/",
    response_model=MinLovelaceResponse,
    status_code=200,
    summary="Calculate minimum ADA required for a UTXO",
    description="Given UTXO output details (address, assets, datum), calculate the minimum lovelace required per Cardano protocol.",
    responses={
        400: {"model": TransactionErrorResponse, "description": "Invalid address or asset format"},
        401: {"model": TransactionErrorResponse, "description": "Authentication required"},
        500: {"model": TransactionErrorResponse, "description": "Failed to calculate min lovelace"},
    },
)
async def calculate_min_lovelace(
    request: AddressDestin,
    _tenant: str = Depends(require_tenant_context),
    chain_context: CardanoChainContext = Depends(get_chain_context),
) -> MinLovelaceResponse:
    """
    Calculate minimum lovelace required for a UTXO output.

    This endpoint calculates the minimum ADA (lovelace) required for a UTXO based on:
    - Address size and type
    - Native tokens (multiAsset) if present
    - Datum if attached
    - Current Cardano protocol parameters

    **Authentication Required:**
    - API key header (X-API-Key)

    **Use cases:**
    - Determine min ADA before creating transaction outputs
    - Validate if a UTXO will meet minimum requirements
    - Calculate proper ADA amounts for NFT/token transfers

    **Example:**
    ```json
    {
      "address": "addr_test1...",
      "lovelace": 0,
      "multiAsset": [
        {
          "policyid": "abc123...",
          "tokens": {"TokenName": 1}
        }
      ],
      "datum": null
    }
    ```
    """
    try:
        # Validate and parse address
        try:
            address = pc.Address.from_primitive(request.address)
        except Exception as e:
            raise HTTPException(
                status_code=400,
                detail=f"Invalid Cardano address format: {str(e)}"
            )

        # Build multiAsset if provided
        multi_asset = None
        if request.multiAsset:
            multi_asset_dict = {}
            for item in request.multiAsset:
                # Convert policy ID from hex string to ScriptHash
                policy_id = pc.ScriptHash.from_primitive(item.policyid)

                # Build assets dict for this policy
                assets_dict = {}
                for token_name, amount in item.tokens.items():
                    # Try to parse token name as hex, fallback to UTF-8 encoding
                    try:
                        asset_name = pc.AssetName(bytes.fromhex(token_name))
                    except ValueError:
                        asset_name = pc.AssetName(token_name.encode('utf-8'))
                    assets_dict[asset_name] = amount

                multi_asset_dict[policy_id] = pc.Asset(assets_dict)

            multi_asset = pc.MultiAsset(multi_asset_dict)

        # Create Value
        if multi_asset:
            amount = pc.Value(coin=request.lovelace, multi_asset=multi_asset)
        else:
            amount = pc.Value(coin=request.lovelace)

        # Parse datum if provided
        datum = None
        if request.datum:
            if isinstance(request.datum, str):
                # Assume CBOR hex string
                datum = pc.Datum(pc.RawCBOR(bytes.fromhex(request.datum)))
            else:
                # Assume dict - convert to datum
                datum = pc.Datum(request.datum)

        # Create output for min lovelace calculation
        output = pc.TransactionOutput(address=address, amount=amount, datum=datum)

        # Calculate min lovelace using PyCardano
        context = chain_context.get_context()
        min_val = pc.min_lovelace(context, output=output)

        return MinLovelaceResponse(
            min_lovelace=min_val,
            min_ada=min_val / 1_000_000
        )

    except ValueError as e:
        raise HTTPException(status_code=400, detail=f"Invalid input: {str(e)}") from e
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to calculate min lovelace: {str(e)}") from e


# ============================================================================
# Blockchain Transaction History Endpoint
# ============================================================================


@router.get(
    "/address-history/",
    response_model=BlockchainTransactionHistoryResponse,
    status_code=200,
    summary="Get transaction history from blockchain",
    description="Query transaction history directly from Cardano blockchain via Blockfrost API for any Cardano address",
    responses={
        400: {"model": TransactionErrorResponse, "description": "Invalid address or parameters"},
        401: {"model": TransactionErrorResponse, "description": "Authentication required"},
        500: {"model": TransactionErrorResponse, "description": "Failed to query blockchain"},
    },
)
async def get_blockchain_transaction_history(
    address: str = Query(..., description="Cardano address to query transaction history for"),
    wallet: WalletAuthContext = Depends(get_wallet_from_token),
    from_block: str | None = Query(None, description="Starting block height (inclusive)"),
    to_block: str | None = Query(None, description="Ending block height (inclusive)"),
    page: int = Query(1, ge=1, le=1000, description="Page number (1-1000)"),
    limit: int = Query(10, ge=1, le=100, description="Results per page (1-100)"),
    chain_context: CardanoChainContext = Depends(get_chain_context),
) -> BlockchainTransactionHistoryResponse:
    """
    Get transaction history from Cardano blockchain for any address.

    This endpoint queries the blockchain directly via Blockfrost API, providing:
    - Complete transaction history for any Cardano address (sent and received)
    - Full UTXO details with native asset information
    - Transaction metadata from on-chain data
    - Block confirmation details

    **Key Differences from /history:**
    - Queries blockchain, not local database
    - Accepts any Cardano address (not limited to wallet's own addresses)
    - Shows ALL transactions for the address, not just ones created via this API
    - Includes full multi-asset details
    - Only shows confirmed transactions (on-chain)

    **Authentication Required:**
    - JWT token from unlocked wallet (for rate limiting and access control)

    **Pagination:**
    - `page`: Page number to fetch (1-based)
    - `limit`: Results per page (max 100)

    **Block Filtering:**
    - `from_block`: Include transactions from this block height onwards
    - `to_block`: Include transactions up to this block height

    **Example:**
    ```
    GET /transactions/address-history/?address=addr_test1...&page=1&limit=10
    ```
    """
    try:
        # Validate address format
        try:
            pc.Address.from_primitive(address)
        except Exception as e:
            raise HTTPException(status_code=400, detail=f"Invalid Cardano address: {str(e)}")

        # Get Blockfrost API instance
        api = chain_context.get_api()

        # Query address transactions from Blockfrost
        try:
            transactions_list = api.address_transactions(
                address=address,
                from_block=from_block,
                to_block=to_block,
                return_type="json",
                count=limit,
                page=page,
                order="desc",  # Most recent first
            )
        except ApiError as e:
            if "404" in str(e):
                # Address has no transactions yet
                return BlockchainTransactionHistoryResponse(
                    transactions=[],
                    total=0,
                    page=page,
                    limit=limit,
                    has_more=False,
                )
            raise HTTPException(status_code=500, detail=f"Blockfrost API error: {str(e)}")

        # Enrich each transaction with full details
        enriched_transactions = []
        for tx_summary in transactions_list:
            tx_hash = tx_summary["tx_hash"]

            try:
                # Get full transaction details
                tx_utxos = api.transaction_utxos(tx_hash, return_type="json")
                tx_details = api.transaction(tx_hash, return_type="json")

                # Get metadata (may be empty)
                try:
                    tx_metadata = api.transaction_metadata(tx_hash, return_type="json")
                except ApiError:
                    tx_metadata = None

                # Build explorer URL
                explorer_url = chain_context.get_explorer_url(tx_hash)

                # Create enriched transaction item
                enriched_tx = BlockchainTransactionItem(
                    hash=tx_hash,
                    block_height=tx_summary["block_height"],
                    block_time=tx_summary["block_time"],
                    block=tx_details.get("block", ""),
                    slot=tx_details.get("slot", 0),
                    inputs=tx_utxos.get("inputs", []),
                    outputs=tx_utxos.get("outputs", []),
                    fees=tx_details.get("fees", "0"),
                    size=tx_details.get("size", 0),
                    index=tx_details.get("index", 0),
                    output_amount=tx_details.get("output_amount", []),
                    deposit=tx_details.get("deposit", "0"),
                    metadata=tx_metadata,
                    invalid_before=tx_details.get("invalid_before"),
                    invalid_hereafter=tx_details.get("invalid_hereafter"),
                    valid_contract=tx_details.get("valid_contract", True),
                    explorer_url=explorer_url,
                )

                enriched_transactions.append(enriched_tx)

            except ApiError as e:
                # Log error but continue with other transactions
                print(f"Warning: Failed to enrich transaction {tx_hash}: {str(e)}")
                continue

        # Determine if there are more results
        has_more = len(transactions_list) == limit

        return BlockchainTransactionHistoryResponse(
            transactions=enriched_transactions,
            total=len(enriched_transactions),
            page=page,
            limit=limit,
            has_more=has_more,
        )

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to query blockchain transaction history: {str(e)}"
        )

