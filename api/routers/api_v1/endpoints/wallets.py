"""
Wallet Endpoints

FastAPI endpoints for wallet management operations.
Provides wallet information, balance checking, address generation, and switching.
"""

import os
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Path, Query
from sqlalchemy.ext.asyncio import AsyncSession

from api.database.connection import get_session
from api.dependencies.auth import require_core_wallet, WalletAuthContext
from api.enums import NetworkType, WalletRole
from api.schemas.wallet import (
    CreateWalletRequest,
    CreateWalletResponse,
    DerivedAddressInfo,
    ErrorResponse,
    GenerateAddressesRequest,
    GenerateAddressesResponse,
    ImportWalletRequest,
    ImportWalletResponse,
    LockWalletResponse,
    RefreshTokenRequest,
    RefreshTokenResponse,
    UnlockWalletRequest,
    UnlockWalletResponse,
    WalletAddressInfo,
    WalletBalanceInfo,
    WalletBalanceResponse,
    WalletBalances,
    WalletExportData,
    WalletExportResponse,
    WalletInfoResponse,
    WalletListItem,
    WalletListResponse,
)
from api.services.session_manager import get_session_manager
from api.services.token_service import InvalidTokenError, TokenService
from api.services.wallet_service import (
    InvalidMnemonicError,
    InvalidPasswordError,
    WalletAlreadyExistsError,
    WalletNotFoundError,
    WalletService,
)
from cardano_offchain.chain_context import CardanoChainContext
from cardano_offchain.wallet import WalletManager


router = APIRouter()

# Global state for wallet management
_wallet_manager: WalletManager | None = None
_chain_context: CardanoChainContext | None = None


# ============================================================================
# Dependencies
# ============================================================================


def get_wallet_manager() -> WalletManager:
    """Get or initialize the wallet manager"""
    global _wallet_manager
    if _wallet_manager is None:
        network = os.getenv("network", "testnet")
        _wallet_manager = WalletManager.from_environment(network)
        if not _wallet_manager.get_wallet_names():
            raise HTTPException(
                status_code=500,
                detail="No wallets configured. Set wallet_mnemonic or wallet_mnemonic_<role> environment variables",
            )
    return _wallet_manager


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
# Wallet Creation & Import Endpoints
# ============================================================================


@router.post(
    "/create",
    response_model=CreateWalletResponse,
    summary="Create a new wallet",
    description="Generate a new wallet with a 24-word BIP39 mnemonic. The mnemonic is shown ONCE and must be saved securely.",
    responses={
        400: {"model": ErrorResponse, "description": "Invalid request (weak password, duplicate name, etc.)"},
        500: {"model": ErrorResponse, "description": "Server error"},
    },
)
async def create_wallet(
    request: CreateWalletRequest,
    session: AsyncSession = Depends(get_session),
) -> CreateWalletResponse:
    """
    Create a new wallet with generated mnemonic.

    **IMPORTANT**: The mnemonic phrase is returned ONLY ONCE. Save it securely!
    You will need it to recover your wallet if you forget your password.

    **Password Requirements:**
    - Minimum 8 characters
    - At least one uppercase letter
    - At least one lowercase letter
    - At least one digit
    - At least one special character (!@#$%^&*...)

    **Mnemonic Details:**
    - 24 words (256-bit entropy)
    - BIP39 standard
    - Encrypted with password before storage
    """
    try:
        # Validate network
        try:
            network = NetworkType(request.network)
        except ValueError:
            raise HTTPException(
                status_code=400,
                detail=f"Invalid network '{request.network}'. Must be 'testnet' or 'mainnet'"
            )

        # Create wallet service
        wallet_service = WalletService(session)

        # Create wallet (returns wallet and mnemonic)
        wallet, mnemonic = await wallet_service.create_wallet(
            name=request.name,
            password=request.password,
            network=network
        )

        # Return response with mnemonic (SHOWN ONLY ONCE!)
        return CreateWalletResponse(
            success=True,
            wallet_id=wallet.id,  # type: ignore
            name=wallet.name,
            network=wallet.network.value,
            role=wallet.wallet_role.value,
            enterprise_address=wallet.enterprise_address,
            staking_address=wallet.staking_address,
            mnemonic=mnemonic,
            created_at=wallet.created_at,
        )

    except WalletAlreadyExistsError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except ValueError as e:
        # Password validation or other value errors
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to create wallet: {str(e)}")


@router.post(
    "/import",
    response_model=ImportWalletResponse,
    summary="Import an existing wallet",
    description="Import a wallet from an existing BIP39 mnemonic phrase",
    responses={
        400: {"model": ErrorResponse, "description": "Invalid request (weak password, invalid mnemonic, etc.)"},
        500: {"model": ErrorResponse, "description": "Server error"},
    },
)
async def import_wallet(
    request: ImportWalletRequest,
    session: AsyncSession = Depends(get_session),
) -> ImportWalletResponse:
    """
    Import an existing wallet from a mnemonic phrase.

    **Password Requirements:**
    - Minimum 8 characters
    - At least one uppercase letter
    - At least one lowercase letter
    - At least one digit
    - At least one special character (!@#$%^&*...)

    **Mnemonic:**
    - Must be a valid BIP39 mnemonic (12-24 words)
    - Space-separated words
    - Words will be encrypted with your password
    """
    try:
        # Validate network
        try:
            network = NetworkType(request.network)
        except ValueError:
            raise HTTPException(
                status_code=400,
                detail=f"Invalid network '{request.network}'. Must be 'testnet' or 'mainnet'"
            )

        # Create wallet service
        wallet_service = WalletService(session)

        # Import wallet
        wallet = await wallet_service.import_wallet(
            name=request.name,
            mnemonic=request.mnemonic.strip(),
            password=request.password,
            network=network
        )

        # Return response
        return ImportWalletResponse(
            success=True,
            wallet_id=wallet.id,  # type: ignore
            name=wallet.name,
            network=wallet.network.value,
            role=wallet.wallet_role.value,
            enterprise_address=wallet.enterprise_address,
            staking_address=wallet.staking_address,
            imported_at=wallet.created_at,
        )

    except WalletAlreadyExistsError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except InvalidMnemonicError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except ValueError as e:
        # Password validation or other value errors
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to import wallet: {str(e)}")


# ============================================================================
# Session Management Endpoints
# ============================================================================


@router.post(
    "/{payment_key_hash}/unlock",
    response_model=UnlockWalletResponse,
    summary="Unlock a wallet",
    description="Unlock a wallet with password to create an authenticated session for signing transactions",
    responses={
        400: {"model": ErrorResponse, "description": "Invalid request"},
        401: {"model": ErrorResponse, "description": "Incorrect password"},
        404: {"model": ErrorResponse, "description": "Wallet not found"},
        500: {"model": ErrorResponse, "description": "Server error"},
    },
)
async def unlock_wallet(
    payment_key_hash: str = Path(..., description="Payment key hash (wallet ID) to unlock"),
    request: UnlockWalletRequest = ...,
    session: AsyncSession = Depends(get_session),
) -> UnlockWalletResponse:
    """
    Unlock a wallet with password.

    This endpoint:
    1. Validates the password
    2. Decrypts the wallet mnemonic
    3. Creates an in-memory CardanoWallet instance
    4. Generates JWT access and refresh tokens
    5. Stores the session for transaction signing

    **Security:**
    - Access token expires in 30 minutes (configurable)
    - Refresh token expires in 7 days (configurable)
    - Tokens are required for transaction signing
    - Use access token in Authorization header: `Bearer <token>`

    **Usage:**
    - Save both tokens securely
    - Use access token for API calls
    - Use refresh token to get new access tokens when they expire
    - Lock wallet when done to clear the session
    """
    try:
        wallet_service = WalletService(session)

        # Unlock wallet and get CardanoWallet instance
        wallet, cardano_wallet = await wallet_service.unlock_wallet(payment_key_hash, request.password)

        # Generate tokens
        access_token, access_jti, access_expires_at = TokenService.create_wallet_token(
            payment_key_hash=wallet.payment_key_hash,
            wallet_name=wallet.name,
            wallet_role=wallet.wallet_role,
        )

        refresh_token, refresh_jti, refresh_expires_at = TokenService.create_refresh_token(
            payment_key_hash=wallet.payment_key_hash,
            wallet_name=wallet.name,
        )

        # Store session in memory (for transaction signing)
        session_manager = get_session_manager()
        session_manager.store_session(
            jti=access_jti,
            cardano_wallet=cardano_wallet,
            expires_at=access_expires_at,
        )

        # Store session in database (for audit trail and revocation)
        from api.database.models import WalletSession

        db_session = WalletSession(
            wallet_id=wallet.payment_key_hash,
            jti=access_jti,
            refresh_jti=refresh_jti,
            expires_at=access_expires_at.replace(tzinfo=None),  # Remove timezone for DB
            refresh_expires_at=refresh_expires_at.replace(tzinfo=None),
            created_at=datetime.now(timezone.utc).replace(tzinfo=None),
            last_used_at=datetime.now(timezone.utc).replace(tzinfo=None),
            revoked=False,
        )
        session.add(db_session)
        await session.commit()

        # Calculate expires_in (seconds)
        now = datetime.now(timezone.utc)
        expires_in = int((access_expires_at - now).total_seconds())

        return UnlockWalletResponse(
            success=True,
            wallet_id=wallet.payment_key_hash,
            wallet_name=wallet.name,
            wallet_role=wallet.wallet_role.value,
            access_token=access_token,
            refresh_token=refresh_token,
            expires_in=expires_in,
            expires_at=access_expires_at,
        )

    except WalletNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except InvalidPasswordError as e:
        raise HTTPException(status_code=401, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to unlock wallet: {str(e)}")


@router.post(
    "/{payment_key_hash}/lock",
    response_model=LockWalletResponse,
    summary="Lock a wallet",
    description="Lock a wallet and revoke all active sessions",
    responses={
        404: {"model": ErrorResponse, "description": "Wallet not found"},
        500: {"model": ErrorResponse, "description": "Server error"},
    },
)
async def lock_wallet(
    payment_key_hash: str = Path(..., description="Payment key hash (wallet ID) to lock"),
    session: AsyncSession = Depends(get_session),
) -> LockWalletResponse:
    """
    Lock a wallet and revoke all sessions.

    This endpoint:
    1. Removes the in-memory CardanoWallet instance
    2. Revokes all database sessions for this wallet
    3. Updates the wallet lock status

    **Security:**
    - All access tokens for this wallet are invalidated
    - Wallet must be unlocked again to sign transactions
    - Recommended when done using the wallet
    """
    try:
        wallet_service = WalletService(session)

        # Lock wallet in database
        wallet = await wallet_service.lock_wallet(payment_key_hash)

        # Revoke all sessions in database
        from sqlalchemy import update

        from api.database.models import WalletSession

        stmt = (
            update(WalletSession)
            .where(WalletSession.wallet_id == payment_key_hash, WalletSession.revoked == False)  # noqa: E712
            .values(revoked=True)
        )
        await session.execute(stmt)
        await session.commit()

        # Get all JTIs for this wallet to remove from memory
        # Note: This is a simplified approach. In production, you might want to
        # maintain a wallet_id -> [jti] mapping for efficiency
        from sqlalchemy import select

        stmt_select = select(WalletSession.jti).where(WalletSession.wallet_id == payment_key_hash)
        result = await session.execute(stmt_select)
        jtis = [row[0] for row in result.fetchall()]

        # Remove sessions from memory
        session_manager = get_session_manager()
        for jti in jtis:
            session_manager.remove_session(jti)

        return LockWalletResponse(
            success=True,
            wallet_id=wallet.payment_key_hash,
            wallet_name=wallet.name,
            message=f"Wallet '{wallet.name}' locked successfully. All sessions revoked.",
        )

    except WalletNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to lock wallet: {str(e)}")


@router.post(
    "/token/refresh",
    response_model=RefreshTokenResponse,
    summary="Refresh access token",
    description="Use a refresh token to obtain a new access token",
    responses={
        401: {"model": ErrorResponse, "description": "Invalid or expired refresh token"},
        500: {"model": ErrorResponse, "description": "Server error"},
    },
)
async def refresh_access_token(
    request: RefreshTokenRequest,
    session: AsyncSession = Depends(get_session),
) -> RefreshTokenResponse:
    """
    Refresh an access token using a refresh token.

    This endpoint:
    1. Validates the refresh token
    2. Checks that the session hasn't been revoked
    3. Generates a new access token
    4. Extends the session in memory

    **Usage:**
    - Call this endpoint when your access token expires
    - Use the refresh token obtained from the unlock endpoint
    - Receive a new access token with fresh expiration
    - The refresh token remains valid until its expiration

    **Security:**
    - Refresh tokens are long-lived (7 days by default)
    - If refresh token expires, wallet must be unlocked again
    - Locking a wallet revokes all refresh tokens
    """
    try:
        # Verify refresh token
        try:
            payload = TokenService.verify_token(request.refresh_token, expected_type="refresh")
        except InvalidTokenError as e:
            raise HTTPException(status_code=401, detail=f"Invalid or expired refresh token: {str(e)}")

        # Extract token data
        wallet_id = payload["wallet_id"]
        wallet_name = payload["wallet_name"]
        refresh_jti = payload["jti"]

        # Check if session is still valid in database
        from sqlalchemy import select

        from api.database.models import WalletSession

        stmt = select(WalletSession).where(
            WalletSession.refresh_jti == refresh_jti,
            WalletSession.wallet_id == wallet_id,
            WalletSession.revoked == False,  # noqa: E712
        )
        result = await session.execute(stmt)
        db_session = result.scalar_one_or_none()

        if not db_session:
            raise HTTPException(
                status_code=401,
                detail="Session not found or has been revoked. Please unlock the wallet again.",
            )

        # Check if refresh token expired
        if db_session.refresh_expires_at < datetime.now(timezone.utc).replace(tzinfo=None):
            raise HTTPException(
                status_code=401, detail="Refresh token expired. Please unlock the wallet again."
            )

        # Get wallet to get role
        wallet_service = WalletService(session)
        wallet = await wallet_service.get_wallet(wallet_id)

        # Generate new access token
        new_access_token, new_access_jti, new_access_expires_at = TokenService.create_wallet_token(
            wallet_id=wallet_id,
            wallet_name=wallet_name,
            wallet_role=wallet.wallet_role,
        )

        # Get the CardanoWallet instance from the old session (if still exists)
        session_manager = get_session_manager()
        cardano_wallet = session_manager.get_session(db_session.jti)

        if not cardano_wallet:
            # Session expired in memory, need to re-unlock
            raise HTTPException(
                status_code=401,
                detail="Session expired in memory. Please unlock the wallet again with your password.",
            )

        # Store new session in memory
        session_manager.store_session(
            jti=new_access_jti,
            cardano_wallet=cardano_wallet,
            expires_at=new_access_expires_at,
        )

        # Update database session with new JTI
        db_session.jti = new_access_jti
        db_session.expires_at = new_access_expires_at.replace(tzinfo=None)
        db_session.last_used_at = datetime.now(timezone.utc).replace(tzinfo=None)
        await session.commit()

        # Calculate expires_in
        now = datetime.now(timezone.utc)
        expires_in = int((new_access_expires_at - now).total_seconds())

        return RefreshTokenResponse(
            success=True,
            access_token=new_access_token,
            expires_in=expires_in,
            expires_at=new_access_expires_at,
        )

    except HTTPException:
        raise
    except WalletNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to refresh token: {str(e)}")


# ============================================================================
# Wallet List & Info Endpoints
# ============================================================================


@router.get(
    "/",
    response_model=WalletListResponse,
    summary="List all wallets",
    description="Get a list of all database wallets with basic information",
)
async def list_wallets(
    session: AsyncSession = Depends(get_session),
) -> WalletListResponse:
    """
    List all database wallets.

    Returns only wallets stored in the database. Environment variables are no longer
    supported for wallet storage. Use the /migrate-from-env endpoint to migrate
    legacy environment wallets to the database.

    **Features:**
    - Shows wallet ID, name, addresses, role (USER/CORE)
    - Indicates lock status
    - Shows default wallet
    """
    try:
        # Get database wallets only
        wallet_service = WalletService(session)
        db_wallets = await wallet_service.list_wallets(skip=0, limit=100)

        wallets = []
        default_wallet_name = None

        for db_wallet in db_wallets:
            wallets.append(
                WalletListItem(
                    id=db_wallet.id,
                    name=db_wallet.name,
                    network=db_wallet.network.value,
                    enterprise_address=db_wallet.enterprise_address,
                    is_default=db_wallet.is_default,
                    source="database",  # All wallets are from database now
                    role=db_wallet.wallet_role.value,
                    is_locked=db_wallet.is_locked,
                )
            )

            # Track default wallet
            if db_wallet.is_default:
                default_wallet_name = db_wallet.name

        return WalletListResponse(
            wallets=wallets,
            total=len(wallets),
            default_wallet=default_wallet_name
        )

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to list wallets: {str(e)}")


@router.get(
    "/{wallet_name}",
    response_model=WalletInfoResponse,
    summary="Get wallet details",
    description="Get detailed information about a specific wallet including addresses",
    responses={404: {"model": ErrorResponse, "description": "Wallet not found"}},
)
async def get_wallet_info(
    wallet_name: str = Path(..., description="Name of the wallet to retrieve"),
    wallet_manager: WalletManager = Depends(get_wallet_manager),
) -> WalletInfoResponse:
    """
    Get detailed information about a specific wallet.

    Returns:
    - Main addresses (enterprise and staking)
    - Derived addresses (if any have been generated)
    - Network type
    - Whether this is the default wallet
    """
    try:
        wallet = wallet_manager.get_wallet(wallet_name)
        if not wallet:
            raise HTTPException(status_code=404, detail=f"Wallet '{wallet_name}' not found")

        default_wallet_name = wallet_manager.get_default_wallet_name()

        # Get wallet info
        wallet_info = wallet.get_wallet_info()

        # Convert to response format
        main_addresses = WalletAddressInfo(
            enterprise=wallet_info["main_addresses"]["enterprise"], staking=wallet_info["main_addresses"]["staking"]
        )

        derived_addresses = [
            DerivedAddressInfo(
                index=addr["index"],
                path=addr["path"],
                enterprise_address=addr["enterprise_address"],
                staking_address=addr["staking_address"],
            )
            for addr in wallet_info["derived_addresses"]
        ]

        return WalletInfoResponse(
            name=wallet_name,
            network=wallet_info["network"],
            main_addresses=main_addresses,
            derived_addresses=derived_addresses,
            is_default=(wallet_name == default_wallet_name),
        )

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get wallet info: {str(e)}")


# ============================================================================
# Wallet Operations Endpoints
# ============================================================================


@router.post(
    "/{wallet_name}/addresses/generate",
    response_model=GenerateAddressesResponse,
    summary="Generate new addresses",
    description="Generate new derived addresses for a wallet",
    responses={404: {"model": ErrorResponse, "description": "Wallet not found"}},
)
async def generate_addresses(
    wallet_name: str = Path(..., description="Name of the wallet"),
    request: GenerateAddressesRequest = GenerateAddressesRequest(),
    wallet_manager: WalletManager = Depends(get_wallet_manager),
) -> GenerateAddressesResponse:
    """
    Generate new derived addresses for a wallet.

    Creates new payment addresses following the BIP44 derivation standard.
    Each address has both an enterprise version (payment only) and a staking version.
    """
    try:
        wallet = wallet_manager.get_wallet(wallet_name)
        if not wallet:
            raise HTTPException(status_code=404, detail=f"Wallet '{wallet_name}' not found")

        # Generate addresses
        generated = wallet.generate_addresses(request.count)

        # Convert to response format
        addresses = [
            DerivedAddressInfo(
                index=addr["index"],
                path=addr["derivation_path"],
                enterprise_address=str(addr["enterprise_address"]),
                staking_address=str(addr["staking_address"]),
            )
            for addr in generated
        ]

        return GenerateAddressesResponse(wallet_name=wallet_name, addresses=addresses, count=len(addresses))

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to generate addresses: {str(e)}")


# ============================================================================
# Balance Endpoints
# ============================================================================


@router.get(
    "/{wallet_name}/balances",
    response_model=WalletBalanceResponse,
    summary="Check wallet balances",
    description="Get balance information for a wallet including main and derived addresses",
    responses={404: {"model": ErrorResponse, "description": "Wallet not found"}},
)
async def check_wallet_balances(
    wallet_name: str = Path(..., description="Name of the wallet"),
    limit_addresses: int = Query(5, ge=1, le=20, description="Number of derived addresses to check (1-20)"),
    wallet_manager: WalletManager = Depends(get_wallet_manager),
    chain_context: CardanoChainContext = Depends(get_chain_context),
) -> WalletBalanceResponse:
    """
    Check balances for a wallet.

    Queries the blockchain for current balances across:
    - Main enterprise address
    - Main staking address
    - Derived addresses (up to specified limit)

    Returns total balance across all addresses.
    """
    try:
        wallet = wallet_manager.get_wallet(wallet_name)
        if not wallet:
            raise HTTPException(status_code=404, detail=f"Wallet '{wallet_name}' not found")

        # Get API for balance checking
        api = chain_context.get_api()

        # Check balances
        balance_data = wallet.check_balances(api, limit_addresses=limit_addresses)

        # Convert to response format
        main_addresses_balance = {
            "enterprise": WalletBalanceInfo(
                address=balance_data["main_addresses"]["enterprise"]["address"],
                balance_lovelace=balance_data["main_addresses"]["enterprise"]["balance"],
                balance_ada=balance_data["main_addresses"]["enterprise"]["balance"] / 1_000_000,
            ),
            "staking": WalletBalanceInfo(
                address=balance_data["main_addresses"]["staking"]["address"],
                balance_lovelace=balance_data["main_addresses"]["staking"].get("balance", 0),
                balance_ada=balance_data["main_addresses"]["staking"].get("balance", 0) / 1_000_000,
            ),
        }

        derived_addresses_balance = [
            WalletBalanceInfo(
                address=addr["address"], balance_lovelace=addr["balance"], balance_ada=addr["balance"] / 1_000_000
            )
            for addr in balance_data["derived_addresses"]
        ]

        balances = WalletBalances(
            main_addresses=main_addresses_balance,
            derived_addresses=derived_addresses_balance,
            total_balance_lovelace=balance_data["total_balance"],
            total_balance_ada=balance_data["total_balance"] / 1_000_000,
        )

        return WalletBalanceResponse(wallet_name=wallet_name, balances=balances, checked_at=datetime.now(timezone.utc))

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to check balances: {str(e)}")


# ============================================================================
# Export Endpoint
# ============================================================================


@router.get(
    "/export",
    response_model=WalletExportResponse,
    summary="Export wallet data",
    description="Export all wallet information to JSON format",
)
async def export_wallets(wallet_manager: WalletManager = Depends(get_wallet_manager)) -> WalletExportResponse:
    """
    Export all wallet data.

    Returns complete wallet information for all configured wallets,
    suitable for backup or external use.

    Does NOT include sensitive information like mnemonics or private keys.
    """
    try:
        wallet_names = wallet_manager.get_wallet_names()
        wallet_data_list = []

        for name in wallet_names:
            wallet = wallet_manager.get_wallet(name)
            if wallet:
                wallet_info = wallet.get_wallet_info()

                main_addresses = WalletAddressInfo(
                    enterprise=wallet_info["main_addresses"]["enterprise"],
                    staking=wallet_info["main_addresses"]["staking"],
                )

                derived_addresses = [
                    DerivedAddressInfo(
                        index=addr["index"],
                        path=addr["path"],
                        enterprise_address=addr["enterprise_address"],
                        staking_address=addr["staking_address"],
                    )
                    for addr in wallet_info["derived_addresses"]
                ]

                wallet_data_list.append(
                    WalletExportData(
                        name=name,
                        network=wallet_info["network"],
                        addresses=main_addresses,
                        derived_addresses=derived_addresses,
                        created_at=None,  # TODO: Get from database when integrated
                    )
                )

        return WalletExportResponse(
            export_timestamp=datetime.now(timezone.utc), wallets=wallet_data_list, total_wallets=len(wallet_data_list)
        )

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to export wallets: {str(e)}")
