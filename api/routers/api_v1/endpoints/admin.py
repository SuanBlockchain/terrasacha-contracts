"""
Admin Endpoints

Administrative endpoints for session monitoring and management.
Protected by CORE wallet authentication and API key.
"""

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Path
from sqlalchemy import select, update, func
from sqlalchemy.ext.asyncio import AsyncSession

from api.database.connection import get_session
from api.database.models import WalletSession, Wallet
from api.dependencies.auth import require_core_wallet, WalletAuthContext
from api.schemas.wallet import (
    AdminSessionListResponse,
    AdminSessionCountResponse,
    AdminCleanupResponse,
    AdminRevokeSessionResponse,
    AdminClearAllResponse,
    SessionMetadata,
    ErrorResponse,
)
from api.services.session_manager import get_session_manager


router = APIRouter()


# ============================================================================
# Session Monitoring Endpoints
# ============================================================================


@router.get(
    "/sessions",
    response_model=AdminSessionListResponse,
    summary="List all sessions",
    description="Get a list of all wallet sessions with metadata (CORE wallets only)",
    responses={
        403: {"model": ErrorResponse, "description": "Access denied - CORE wallet required"},
        500: {"model": ErrorResponse, "description": "Server error"},
    },
)
async def list_sessions(
    admin: WalletAuthContext = Depends(require_core_wallet),
    session: AsyncSession = Depends(get_session),
) -> AdminSessionListResponse:
    """
    List all wallet sessions (active and revoked).

    **Access Control:**
    - Requires CORE wallet authentication
    - Requires valid API key

    **Returns:**
    - All database sessions with metadata
    - Indicates which sessions are still in memory
    - Shows expiration times and usage statistics
    """
    try:
        # Get all sessions from database
        stmt = (
            select(WalletSession, Wallet.name)
            .outerjoin(Wallet, WalletSession.wallet_id == Wallet.id)
            .order_by(WalletSession.created_at.desc())
        )
        result = await session.execute(stmt)
        rows = result.all()

        # Get in-memory session JTIs
        session_manager = get_session_manager()

        sessions = []
        active_count = 0
        in_memory_count = 0

        for db_session, wallet_name in rows:
            # Check if session is in memory
            in_memory = session_manager.session_exists(db_session.jti)
            if in_memory:
                in_memory_count += 1

            if not db_session.revoked:
                active_count += 1

            sessions.append(
                SessionMetadata(
                    id=db_session.id,
                    wallet_id=db_session.wallet_id,
                    wallet_name=wallet_name,
                    jti=db_session.jti,
                    refresh_jti=db_session.refresh_jti,
                    created_at=db_session.created_at,
                    expires_at=db_session.expires_at,
                    refresh_expires_at=db_session.refresh_expires_at,
                    last_used_at=db_session.last_used_at,
                    revoked=db_session.revoked,
                    revoked_at=db_session.revoked_at,
                    in_memory=in_memory,
                    ip_address=db_session.ip_address,
                    user_agent=db_session.user_agent,
                )
            )

        return AdminSessionListResponse(
            sessions=sessions,
            total=len(sessions),
            active=active_count,
            in_memory=in_memory_count,
        )

    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to list sessions: {str(e)}"
        )


@router.get(
    "/sessions/count",
    response_model=AdminSessionCountResponse,
    summary="Get session count",
    description="Get count of sessions in various states (CORE wallets only)",
    responses={
        403: {"model": ErrorResponse, "description": "Access denied - CORE wallet required"},
        500: {"model": ErrorResponse, "description": "Server error"},
    },
)
async def get_session_count(
    admin: WalletAuthContext = Depends(require_core_wallet),
    session: AsyncSession = Depends(get_session),
) -> AdminSessionCountResponse:
    """
    Get session statistics.

    **Access Control:**
    - Requires CORE wallet authentication
    - Requires valid API key

    **Returns:**
    - Total sessions in database
    - Active (non-revoked) sessions
    - Sessions currently in memory
    - Expired sessions pending cleanup
    """
    try:
        # Count total sessions
        total_stmt = select(func.count()).select_from(WalletSession)
        total_result = await session.execute(total_stmt)
        total_count = total_result.scalar() or 0

        # Count active sessions
        active_stmt = select(func.count()).select_from(WalletSession).where(
            WalletSession.revoked == False  # noqa: E712
        )
        active_result = await session.execute(active_stmt)
        active_count = active_result.scalar() or 0

        # Count expired sessions
        now = datetime.now(timezone.utc).replace(tzinfo=None)
        expired_stmt = select(func.count()).select_from(WalletSession).where(
            WalletSession.expires_at < now,
            WalletSession.revoked == False  # noqa: E712
        )
        expired_result = await session.execute(expired_stmt)
        expired_count = expired_result.scalar() or 0

        # Count in-memory sessions
        session_manager = get_session_manager()
        in_memory_count = session_manager.get_session_count()

        return AdminSessionCountResponse(
            total_sessions=total_count,
            active_sessions=active_count,
            in_memory_sessions=in_memory_count,
            expired_sessions=expired_count,
        )

    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to count sessions: {str(e)}"
        )


# ============================================================================
# Session Management Endpoints
# ============================================================================


@router.post(
    "/sessions/cleanup",
    response_model=AdminCleanupResponse,
    summary="Manual cleanup trigger",
    description="Manually trigger cleanup of expired sessions (CORE wallets only)",
    responses={
        403: {"model": ErrorResponse, "description": "Access denied - CORE wallet required"},
        500: {"model": ErrorResponse, "description": "Server error"},
    },
)
async def manual_cleanup(
    admin: WalletAuthContext = Depends(require_core_wallet),
    db_session: AsyncSession = Depends(get_session),
) -> AdminCleanupResponse:
    """
    Manually trigger session cleanup.

    This endpoint:
    1. Removes expired sessions from memory
    2. Marks expired sessions as revoked in database
    3. Returns count of cleaned sessions

    **Access Control:**
    - Requires CORE wallet authentication
    - Requires valid API key

    **Note:** Background cleanup runs automatically every 5 minutes,
    but this endpoint allows manual cleanup on demand.
    """
    try:
        # Cleanup memory
        session_manager = get_session_manager()
        memory_cleaned = session_manager.cleanup_expired()

        # Cleanup database - mark expired sessions as revoked
        now = datetime.now(timezone.utc).replace(tzinfo=None)
        stmt = (
            update(WalletSession)
            .where(
                WalletSession.expires_at < now,
                WalletSession.revoked == False  # noqa: E712
            )
            .values(
                revoked=True,
                revoked_at=now
            )
        )
        result = await db_session.execute(stmt)
        db_cleaned = result.rowcount or 0
        await db_session.commit()

        return AdminCleanupResponse(
            success=True,
            cleaned_memory=memory_cleaned,
            cleaned_database=db_cleaned,
            message=f"Cleaned {memory_cleaned} sessions from memory and {db_cleaned} from database",
        )

    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to cleanup sessions: {str(e)}"
        )


@router.delete(
    "/sessions/{jti}",
    response_model=AdminRevokeSessionResponse,
    summary="Force revoke specific session",
    description="Forcefully revoke a specific session by JTI (CORE wallets only)",
    responses={
        403: {"model": ErrorResponse, "description": "Access denied - CORE wallet required"},
        404: {"model": ErrorResponse, "description": "Session not found"},
        500: {"model": ErrorResponse, "description": "Server error"},
    },
)
async def revoke_session(
    jti: str = Path(..., description="JWT ID (jti) of session to revoke"),
    admin: WalletAuthContext = Depends(require_core_wallet),
    session: AsyncSession = Depends(get_session),
) -> AdminRevokeSessionResponse:
    """
    Force revoke a specific session.

    This endpoint:
    1. Marks the session as revoked in database
    2. Removes the session from memory
    3. User's token becomes immediately invalid

    **Access Control:**
    - Requires CORE wallet authentication
    - Requires valid API key

    **Use Cases:**
    - Security incident response
    - Force logout specific user
    - Session management
    """
    try:
        # Revoke in database
        stmt = (
            update(WalletSession)
            .where(WalletSession.jti == jti)
            .values(
                revoked=True,
                revoked_at=datetime.now(timezone.utc).replace(tzinfo=None)
            )
        )
        result = await session.execute(stmt)

        if result.rowcount == 0:
            raise HTTPException(
                status_code=404,
                detail=f"Session with JTI '{jti}' not found"
            )

        await session.commit()

        # Remove from memory
        session_manager = get_session_manager()
        session_manager.remove_session(jti)

        return AdminRevokeSessionResponse(
            success=True,
            jti=jti,
            message=f"Session '{jti}' revoked successfully",
        )

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to revoke session: {str(e)}"
        )


@router.post(
    "/sessions/clear",
    response_model=AdminClearAllResponse,
    summary="Emergency clear all sessions",
    description="Clear ALL sessions from the system (CORE wallets only) - USE WITH CAUTION",
    responses={
        403: {"model": ErrorResponse, "description": "Access denied - CORE wallet required"},
        500: {"model": ErrorResponse, "description": "Server error"},
    },
)
async def clear_all_sessions(
    admin: WalletAuthContext = Depends(require_core_wallet),
    session: AsyncSession = Depends(get_session),
) -> AdminClearAllResponse:
    """
    Emergency: Clear ALL sessions.

    This endpoint:
    1. Revokes ALL sessions in database
    2. Clears ALL sessions from memory
    3. Forces ALL users to re-authenticate

    **Access Control:**
    - Requires CORE wallet authentication
    - Requires valid API key

    **WARNING:**
    - This will log out ALL users (including the admin!)
    - Use only in emergency situations
    - Security breach response
    - System maintenance

    **After calling this:**
    - All users must unlock their wallets again
    - All tokens become invalid immediately
    """
    try:
        # Revoke all sessions in database
        now = datetime.now(timezone.utc).replace(tzinfo=None)
        stmt = (
            update(WalletSession)
            .where(WalletSession.revoked == False)  # noqa: E712
            .values(
                revoked=True,
                revoked_at=now
            )
        )
        result = await session.execute(stmt)
        db_revoked = result.rowcount or 0
        await session.commit()

        # Clear all from memory
        session_manager = get_session_manager()
        memory_cleared = session_manager.clear_all()

        return AdminClearAllResponse(
            success=True,
            cleared_memory=memory_cleared,
            revoked_database=db_revoked,
            message=f"Emergency: Cleared {memory_cleared} sessions from memory and revoked {db_revoked} in database",
            warning="⚠️  All users have been logged out. They must unlock their wallets again.",
        )

    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to clear sessions: {str(e)}"
        )
