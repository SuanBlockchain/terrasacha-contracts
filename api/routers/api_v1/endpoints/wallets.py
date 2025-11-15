"""
Wallet Endpoints

FastAPI endpoints for wallet management operations.
Provides wallet information, balance checking, address generation, and switching.
"""

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Path
from sqlalchemy.ext.asyncio import AsyncSession

from api.database.connection import get_session
from api.dependencies.auth import WalletAuthContext, get_wallet_from_token, require_core_wallet
from api.enums import NetworkType
from api.schemas.wallet import (
    ChangePasswordRequest,
    ChangePasswordResponse,
    CreateWalletRequest,
    CreateWalletResponse,
    DeleteWalletRequest,
    DeleteWalletResponse,
    ErrorResponse,
    ImportWalletRequest,
    ImportWalletResponse,
    LockWalletResponse,
    PromoteWalletResponse,
    RefreshTokenRequest,
    RefreshTokenResponse,
    RevokeTokenResponse,
    UnlockWalletRequest,
    UnlockWalletResponse,
    WalletInfoResponse,
    WalletListItem,
    WalletListResponse,
)
from api.services.session_manager import get_session_manager
from api.services.token_service import InvalidTokenError, TokenService
from api.services.wallet_service import (
    InvalidMnemonicError,
    InvalidPasswordError,
    PermissionDeniedError,
    WalletAlreadyExistsError,
    WalletNotFoundError,
    WalletService,
)


router = APIRouter()


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
            wallet_id=wallet.id,
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
            wallet_id=wallet.id,
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
    "/{wallet_id}/unlock",
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
    wallet_id: str = Path(..., description="Wallet ID to unlock"),
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
        wallet, cardano_wallet = await wallet_service.unlock_wallet(wallet_id, request.password)

        # Generate tokens
        access_token, access_jti, access_expires_at = TokenService.create_wallet_token(
            payment_key_hash=wallet.id,
            wallet_name=wallet.name,
            wallet_role=wallet.wallet_role,
        )

        refresh_token, refresh_jti, refresh_expires_at = TokenService.create_refresh_token(
            payment_key_hash=wallet.id,
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
            wallet_id=wallet.id,
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
            wallet_id=wallet.id,
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
    "/{wallet_id}/lock",
    response_model=LockWalletResponse,
    summary="Lock a wallet",
    description="Lock a wallet and revoke all active sessions",
    responses={
        404: {"model": ErrorResponse, "description": "Wallet not found"},
        500: {"model": ErrorResponse, "description": "Server error"},
    },
)
async def lock_wallet(
    wallet_id: str = Path(..., description="Wallet ID to lock"),
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
        wallet = await wallet_service.lock_wallet(wallet_id)

        # Revoke all sessions in database
        from sqlalchemy import update

        from api.database.models import WalletSession

        stmt = (
            update(WalletSession)
            .where(WalletSession.wallet_id == wallet_id, WalletSession.revoked == False)  # noqa: E712
            .values(revoked=True)
        )
        await session.execute(stmt)
        await session.commit()

        # Get all JTIs for this wallet to remove from memory
        # Note: This is a simplified approach. In production, you might want to
        # maintain a wallet_id -> [jti] mapping for efficiency
        from sqlalchemy import select

        stmt_select = select(WalletSession.jti).where(WalletSession.wallet_id == wallet_id)
        result = await session.execute(stmt_select)
        jtis = [row[0] for row in result.fetchall()]

        # Remove sessions from memory
        session_manager = get_session_manager()
        for jti in jtis:
            session_manager.remove_session(jti)

        return LockWalletResponse(
            success=True,
            wallet_id=wallet.id,
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
            payment_key_hash=wallet_id,
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


@router.post(
    "/token/revoke",
    response_model=RevokeTokenResponse,
    summary="Revoke access token (logout)",
    description="Revoke the current access token and terminate the session",
    responses={
        401: {"model": ErrorResponse, "description": "Invalid or missing token"},
        500: {"model": ErrorResponse, "description": "Server error"},
    },
)
async def revoke_token(
    wallet: WalletAuthContext = Depends(get_wallet_from_token),
    session: AsyncSession = Depends(get_session),
) -> RevokeTokenResponse:
    """
    Revoke the current access token (logout).

    This endpoint:
    1. Extracts the JTI from the authenticated token
    2. Marks the session as revoked in the database
    3. Removes the session from in-memory storage
    4. Invalidates the access token

    **Security:**
    - The token used for this request becomes immediately invalid
    - The associated refresh token is also invalidated
    - User must unlock the wallet again to get new tokens

    **Usage:**
    - Call this endpoint when user wants to logout
    - Include the access token in Authorization header
    - Token becomes invalid immediately after this call
    """
    try:
        jti = wallet.jti
        wallet_id = wallet.wallet_id

        # Revoke session in database
        from sqlalchemy import update
        from api.database.models import WalletSession

        stmt = (
            update(WalletSession)
            .where(WalletSession.jti == jti)
            .values(
                revoked=True,
                revoked_at=datetime.now(timezone.utc).replace(tzinfo=None)
            )
        )
        result = await session.execute(stmt)
        await session.commit()

        # Remove from in-memory session manager
        session_manager = get_session_manager()
        session_manager.remove_session(jti)

        return RevokeTokenResponse(
            success=True,
            message="Token revoked successfully. Session terminated.",
            jti=jti,
        )

    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to revoke token: {str(e)}"
        )


@router.post(
    "/{wallet_id}/change-password",
    response_model=ChangePasswordResponse,
    summary="Change wallet password",
    description="Change the password for a wallet. Requires authentication and old password verification.",
    responses={
        400: {"model": ErrorResponse, "description": "Invalid request (weak password, etc.)"},
        401: {"model": ErrorResponse, "description": "Incorrect old password or not authenticated"},
        403: {"model": ErrorResponse, "description": "Not authorized to change this wallet's password"},
        404: {"model": ErrorResponse, "description": "Wallet not found"},
        500: {"model": ErrorResponse, "description": "Server error"},
    },
)
async def change_password(
    wallet_id: str = Path(..., description="Wallet ID (payment key hash)"),
    request: ChangePasswordRequest = ...,
    wallet_auth: WalletAuthContext = Depends(get_wallet_from_token),
    session: AsyncSession = Depends(get_session),
) -> ChangePasswordResponse:
    """
    Change wallet password.

    This endpoint:
    1. Verifies the user is authenticated and owns the wallet
    2. Verifies the old password is correct
    3. Validates the new password meets strength requirements
    4. Re-encrypts the mnemonic with the new password
    5. Locks the wallet and revokes all active sessions
    6. User must unlock with new password to continue

    **Security:**
    - Requires valid access token (must be unlocked)
    - Only the wallet owner can change their password
    - All sessions are revoked after password change
    - Wallet is automatically locked after password change
    - New password must meet strength requirements

    **Password Requirements:**
    - Minimum 8 characters
    - At least one uppercase letter
    - At least one lowercase letter
    - At least one digit
    - At least one special character (!@#$%^&*...)
    """
    try:
        # Verify the authenticated user owns this wallet
        if wallet_auth.wallet_id != wallet_id:
            raise HTTPException(
                status_code=403,
                detail=f"Not authorized to change password for wallet '{wallet_id}'. "
                       f"You are authenticated as '{wallet_auth.wallet_id}'"
            )

        # Change password using wallet service
        wallet_service = WalletService(session)
        updated_wallet = await wallet_service.change_password(
            payment_key_hash=wallet_id,
            old_password=request.old_password,
            new_password=request.new_password
        )

        # Revoke all sessions for this wallet (security measure)
        from sqlalchemy import update, select
        from api.database.models import WalletSession

        # Get all JTIs for this wallet
        stmt_select = select(WalletSession.jti).where(
            WalletSession.wallet_id == wallet_id,
            WalletSession.revoked == False  # noqa: E712
        )
        result = await session.execute(stmt_select)
        jtis = [row[0] for row in result.fetchall()]

        # Revoke all sessions in database
        stmt_update = (
            update(WalletSession)
            .where(
                WalletSession.wallet_id == wallet_id,
                WalletSession.revoked == False  # noqa: E712
            )
            .values(
                revoked=True,
                revoked_at=datetime.now(timezone.utc).replace(tzinfo=None)
            )
        )
        await session.execute(stmt_update)
        await session.commit()

        # Remove all sessions from memory
        session_manager = get_session_manager()
        for jti in jtis:
            session_manager.remove_session(jti)

        return ChangePasswordResponse(
            success=True,
            message="Password changed successfully. Wallet has been locked and all sessions revoked for security. "
                    "Please unlock with your new password.",
            wallet_id=updated_wallet.id,
            wallet_name=updated_wallet.name,
        )

    except WalletNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except InvalidPasswordError as e:
        raise HTTPException(status_code=401, detail=str(e))
    except ValueError as e:
        # Password strength validation error
        raise HTTPException(status_code=400, detail=str(e))
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to change password: {str(e)}"
        )


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
    "/{wallet_id}",
    response_model=WalletInfoResponse,
    summary="Get wallet details",
    description="Get detailed information about a specific wallet by ID (payment key hash)",
    responses={
        404: {"model": ErrorResponse, "description": "Wallet not found"},
        500: {"model": ErrorResponse, "description": "Server error"},
    },
)
async def get_wallet(
    wallet_id: str = Path(..., description="Wallet ID (payment key hash)"),
    session: AsyncSession = Depends(get_session),
) -> WalletInfoResponse:
    """
    Get detailed wallet information by ID.

    Returns comprehensive wallet information including:
    - Wallet ID (payment key hash)
    - Wallet name and network
    - Enterprise and staking addresses
    - Role (USER/CORE)
    - Lock status
    - Default wallet status
    - Creation timestamp
    """
    try:
        wallet_service = WalletService(session)
        wallet = await wallet_service.get_wallet(wallet_id)

        return WalletInfoResponse(
            id=wallet.id,
            name=wallet.name,
            network=wallet.network.value,
            enterprise_address=wallet.enterprise_address,
            staking_address=wallet.staking_address,
            role=wallet.wallet_role.value,
            is_locked=wallet.is_locked,
            is_default=wallet.is_default,
            created_at=wallet.created_at,
        )

    except WalletNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get wallet: {str(e)}")


@router.delete(
    "/{wallet_id}",
    response_model=DeleteWalletResponse,
    summary="Delete a wallet",
    description="Delete a wallet by ID with password confirmation. CORE wallets require at least one other CORE wallet to exist.",
    responses={
        400: {"model": ErrorResponse, "description": "Invalid request or cannot delete last CORE wallet"},
        401: {"model": ErrorResponse, "description": "Incorrect password"},
        404: {"model": ErrorResponse, "description": "Wallet not found"},
        500: {"model": ErrorResponse, "description": "Server error"},
    },
)
async def delete_wallet(
    wallet_id: str = Path(..., description="Wallet ID (payment key hash)"),
    request: DeleteWalletRequest = ...,
    session: AsyncSession = Depends(get_session),
) -> DeleteWalletResponse:
    """
    Delete a wallet with password confirmation.

    **Security:**
    - Requires the wallet password for confirmation
    - Cannot delete the last CORE wallet (system protection)
    - Cascades to delete all associated sessions

    **Warning:**
    - This action is PERMANENT and cannot be undone
    - Make sure you have backed up your mnemonic phrase
    - All active sessions for this wallet will be terminated
    """
    try:
        wallet_service = WalletService(session)

        # Get wallet info before deletion for response
        wallet = await wallet_service.get_wallet(wallet_id)
        wallet_name = wallet.name

        # Delete wallet (includes password verification)
        await wallet_service.delete_wallet(wallet_id, request.password)

        # Remove any active sessions from memory
        from sqlalchemy import select

        from api.database.models import WalletSession

        stmt = select(WalletSession.jti).where(WalletSession.wallet_id == wallet_id)
        result = await session.execute(stmt)
        jtis = [row[0] for row in result.fetchall()]

        session_manager = get_session_manager()
        for jti in jtis:
            session_manager.remove_session(jti)

        return DeleteWalletResponse(
            success=True,
            message=f"Wallet '{wallet_name}' deleted successfully",
            wallet_id=wallet_id,
        )

    except WalletNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except InvalidPasswordError as e:
        raise HTTPException(status_code=401, detail=str(e))
    except Exception as e:
        # Check if it's a PermissionDeniedError (last CORE wallet)
        if "last CORE wallet" in str(e):
            raise HTTPException(status_code=400, detail=str(e))
        raise HTTPException(status_code=500, detail=f"Failed to delete wallet: {str(e)}")


@router.put(
    "/{wallet_id}/promote",
    response_model=PromoteWalletResponse,
    summary="Promote wallet to CORE role",
    description="Promote a wallet to CORE role, granting administrative privileges. Only CORE wallets can promote other wallets.",
    responses={
        403: {"model": ErrorResponse, "description": "Not authorized (requires CORE wallet)"},
        404: {"model": ErrorResponse, "description": "Wallet not found"},
        500: {"model": ErrorResponse, "description": "Server error"},
    },
)
async def promote_wallet(
    wallet_id: str = Path(..., description="Wallet ID to promote"),
    core_wallet: WalletAuthContext = Depends(require_core_wallet),
    session: AsyncSession = Depends(get_session),
) -> PromoteWalletResponse:
    """
    Promote a wallet to CORE role.

    This endpoint:
    1. Verifies the authenticated user is a CORE wallet
    2. Promotes the target wallet to CORE role
    3. Grants the wallet administrative privileges

    **Security:**
    - Requires authentication with a CORE wallet
    - Only CORE wallets can promote other wallets
    - Promoted wallets can then promote others

    **CORE Wallet Privileges:**
    - Compile smart contracts
    - Promote other wallets to CORE role
    - Administrative operations

    **Usage:**
    - First CORE wallet should be set manually in the database
    - That wallet can then promote others via this endpoint
    """
    try:
        wallet_service = WalletService(session)

        # Promote the wallet
        promoted_wallet = await wallet_service.promote_to_core(
            payment_key_hash=wallet_id,
            promoted_by_pkh=core_wallet.wallet_id
        )

        return PromoteWalletResponse(
            success=True,
            message=f"Wallet '{promoted_wallet.name}' successfully promoted to CORE role",
            wallet_id=promoted_wallet.id,
            wallet_name=promoted_wallet.name,
            new_role=promoted_wallet.wallet_role.value,
            promoted_by=core_wallet.wallet_id,
        )

    except WalletNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except PermissionDeniedError as e:
        raise HTTPException(status_code=403, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to promote wallet: {str(e)}")