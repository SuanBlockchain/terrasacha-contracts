"""
Authentication Dependencies

FastAPI dependencies for wallet authentication using JWT tokens.
Provides middleware to protect endpoints and retrieve unlocked wallets.
"""

from datetime import datetime, timezone
from typing import Annotated

from fastapi import Depends, HTTPException
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials

from api.database.models import WalletSessionMongo
from api.enums import WalletRole
from api.services.session_manager import get_session_manager
from api.services.token_service import InvalidTokenError, TokenService
from cardano_offchain.wallet import CardanoWallet


# HTTP Bearer security scheme for Swagger UI
bearer_scheme = HTTPBearer(auto_error=False)


class WalletAuthContext:
    """
    Context object returned by authentication dependency.

    Contains both the database wallet record and the unlocked CardanoWallet instance.
    """

    def __init__(
        self,
        wallet_id: str,
        wallet_name: str,
        wallet_role: WalletRole,
        cardano_wallet: CardanoWallet,
        jti: str,
        session_id: int | None = None
    ):
        """
        Initialize wallet auth context.

        Args:
            wallet_id: Payment key hash (wallet ID)
            wallet_name: Wallet name
            wallet_role: Wallet role (USER or CORE)
            cardano_wallet: Unlocked CardanoWallet instance for signing
            jti: JWT ID (for session tracking)
            session_id: Database session ID (if stored)
        """
        self.wallet_id = wallet_id  # Now stores payment_key_hash
        self.wallet_name = wallet_name
        self.wallet_role = wallet_role
        self.cardano_wallet = cardano_wallet
        self.jti = jti
        self.session_id = session_id

    def is_core_wallet(self) -> bool:
        """Check if this wallet has CORE role."""
        return self.wallet_role == WalletRole.CORE


async def get_wallet_from_token(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer_scheme)] = None
) -> WalletAuthContext:
    """
    FastAPI dependency to authenticate wallet from JWT token.

    Validates the token, checks session, and returns the unlocked wallet.

    Usage in endpoints:
        @router.post("/protected-endpoint")
        async def my_endpoint(
            wallet: WalletAuthContext = Depends(get_wallet_from_token)
        ):
            # Use wallet.cardano_wallet for signing transactions
            # Use wallet.wallet_id, wallet.wallet_name, wallet.wallet_role for logic
            ...

    Args:
        credentials: HTTP Bearer credentials from Authorization header

    Returns:
        WalletAuthContext with wallet info and CardanoWallet instance

    Raises:
        HTTPException 401: If authentication fails

    Example:
        >>> # In your endpoint
        >>> wallet_context = Depends(get_wallet_from_token)
        >>> cardano_wallet = wallet_context.cardano_wallet
        >>> # Use cardano_wallet to sign transactions
    """
    # Check for bearer token
    if not credentials:
        raise HTTPException(
            status_code=401,
            detail="Missing authorization header. Use 'Authorization: Bearer <token>'"
        )

    token = credentials.credentials

    # Verify token
    try:
        payload = TokenService.verify_token(token, expected_type="access")
    except InvalidTokenError as e:
        raise HTTPException(
            status_code=401,
            detail=f"Invalid or expired token: {str(e)}"
        )

    # Extract token data
    wallet_id = payload["wallet_id"]
    wallet_name = payload["wallet_name"]
    wallet_role_str = payload["wallet_role"]
    jti = payload["jti"]

    # Convert role string to enum
    try:
        wallet_role = WalletRole(wallet_role_str)
    except ValueError:
        raise HTTPException(
            status_code=401,
            detail=f"Invalid wallet role in token: {wallet_role_str}"
        )

    # Check if session exists in memory
    session_manager = get_session_manager()
    cardano_wallet = session_manager.get_session(jti)

    if not cardano_wallet:
        raise HTTPException(
            status_code=401,
            detail="Session expired or wallet locked. Please unlock the wallet again."
        )

    # Verify session in MongoDB database (for audit trail)
    db_session = await WalletSessionMongo.find_one(
        WalletSessionMongo.jti == jti,
        WalletSessionMongo.wallet_id == wallet_id,
        WalletSessionMongo.revoked == False  # noqa: E712
    )

    session_id = None
    if db_session:
        # Check if session expired in database
        if db_session.expires_at < datetime.now(timezone.utc).replace(tzinfo=None):
            # Clean up expired session
            session_manager.remove_session(jti)
            db_session.revoked = True
            await db_session.save()

            raise HTTPException(
                status_code=401,
                detail="Session expired. Please unlock the wallet again."
            )

        # Update last used timestamp
        db_session.last_used_at = datetime.now(timezone.utc).replace(tzinfo=None)
        await db_session.save()
        session_id = str(db_session.id)  # MongoDB ObjectId to string
    else:
        # Session not in database - might have been revoked
        # Remove from memory as well
        session_manager.remove_session(jti)

        raise HTTPException(
            status_code=401,
            detail="Session not found or has been revoked. Please unlock the wallet again."
        )

    # Return auth context
    return WalletAuthContext(
        wallet_id=wallet_id,
        wallet_name=wallet_name,
        wallet_role=wallet_role,
        cardano_wallet=cardano_wallet,
        jti=jti,
        session_id=session_id
    )


async def require_core_wallet(
    wallet: WalletAuthContext = Depends(get_wallet_from_token)
) -> WalletAuthContext:
    """
    FastAPI dependency that requires a CORE wallet.

    Use this for endpoints that should only be accessible to CORE wallets
    (e.g., promoting other wallets, compiling contracts, etc.).

    Usage:
        @router.post("/admin-endpoint")
        async def my_admin_endpoint(
            wallet: WalletAuthContext = Depends(require_core_wallet)
        ):
            # Only CORE wallets can access this endpoint
            ...

    Args:
        wallet: Authenticated wallet context

    Returns:
        WalletAuthContext (only if wallet is CORE)

    Raises:
        HTTPException 403: If wallet is not CORE role

    Example:
        >>> # Endpoint only accessible to CORE wallets
        >>> @router.put("/wallets/{wallet_id}/promote")
        >>> async def promote_wallet(
        ...     core_wallet: WalletAuthContext = Depends(require_core_wallet)
        ... ):
        ...     # Only CORE wallets can promote other wallets
    """
    if not wallet.is_core_wallet():
        raise HTTPException(
            status_code=403,
            detail=f"Access denied. This operation requires a CORE wallet. "
                   f"Your wallet '{wallet.wallet_name}' has role '{wallet.wallet_role.value}'"
        )

    return wallet
