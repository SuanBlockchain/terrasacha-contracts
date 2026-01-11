"""
Tenant Admin Endpoints

Tenant-specific administrative endpoints for session and API key management.
Protected by tenant API key and CORE wallet authentication.

These endpoints allow CORE wallets to manage their tenant's:
- Wallet sessions (monitoring, cleanup, revocation)
- API keys (create, list, revoke)
"""

from datetime import datetime, timezone, timedelta

from fastapi import APIRouter, Depends, HTTPException, Path
from pydantic import BaseModel

from api.dependencies.auth import require_core_wallet, WalletAuthContext
from api.dependencies.tenant import require_tenant_context
from api.services.admin_service_mongo import AdminSessionService
from api.services.session_cleanup_service import get_cleanup_service
from api.schemas.wallet import (
    AdminSessionListResponse,
    AdminSessionCountResponse,
    AdminCleanupResponse,
    AdminWalletSyncResponse,
    AdminRevokeSessionResponse,
    AdminClearAllResponse,
    SessionMetadata,
    ErrorResponse,
)
from api.services.session_manager import get_session_manager
from api.database.models import ApiKey
from api.utils.security import generate_api_key, hash_api_key


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
    tenant_id: str = Depends(require_tenant_context),
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
        # Use admin service
        admin_service = AdminSessionService()
        session_data = await admin_service.list_all_sessions()

        sessions = []
        active_count = 0
        in_memory_count = 0

        for session_doc, wallet_name, in_memory in session_data:
            if in_memory:
                in_memory_count += 1

            if not session_doc.revoked:
                active_count += 1

            sessions.append(
                SessionMetadata(
                    id=str(session_doc.id),  # MongoDB ObjectId to string
                    wallet_id=session_doc.wallet_id,
                    wallet_name=wallet_name,
                    jti=session_doc.jti,
                    refresh_jti=session_doc.refresh_jti,
                    created_at=session_doc.created_at,
                    expires_at=session_doc.expires_at,
                    refresh_expires_at=session_doc.refresh_expires_at,
                    last_used_at=session_doc.last_used_at,
                    revoked=session_doc.revoked,
                    revoked_at=session_doc.revoked_at,
                    in_memory=in_memory,
                    ip_address=session_doc.ip_address,
                    user_agent=session_doc.user_agent,
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
    tenant_id: str = Depends(require_tenant_context),
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
        admin_service = AdminSessionService()
        counts = await admin_service.count_sessions()

        return AdminSessionCountResponse(
            total_sessions=counts["total"],
            active_sessions=counts["active"],
            in_memory_sessions=counts["in_memory"],
            expired_sessions=counts["expired"],
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
    tenant_id: str = Depends(require_tenant_context),
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

    **Note:** This endpoint cleans up session memory and database entries.
    For comprehensive cleanup including wallet locking, use /sessions/sync-wallets instead.
    """
    try:
        admin_service = AdminSessionService()
        result = await admin_service.cleanup_expired_sessions()

        return AdminCleanupResponse(
            success=True,
            cleaned_memory=result["memory_cleaned"],
            cleaned_database=result["db_cleaned"],
            message=f"Cleaned {result['memory_cleaned']} sessions from memory "
                    f"and {result['db_cleaned']} from database",
        )

    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to cleanup sessions: {str(e)}"
        )


@router.post(
    "/sessions/sync-wallets",
    response_model=AdminWalletSyncResponse,
    summary="Synchronize wallet lock state with sessions",
    description="Lock wallets with no active sessions and cleanup expired sessions (CORE wallets only)",
    responses={
        403: {"model": ErrorResponse, "description": "Access denied - CORE wallet required"},
        500: {"model": ErrorResponse, "description": "Server error"},
    },
)
async def sync_wallet_locks(
    admin: WalletAuthContext = Depends(require_core_wallet),
    tenant_id: str = Depends(require_tenant_context),
) -> AdminWalletSyncResponse:
    """
    Synchronize wallet lock state with active sessions.

    This endpoint performs comprehensive cleanup:
    1. Checks all wallets for active sessions
    2. Locks wallets that have no active (non-revoked, non-expired) sessions
    3. Removes expired/revoked sessions from in-memory storage
    4. Ensures database state matches actual session state

    **Access Control:**
    - Requires CORE wallet authentication
    - Requires valid tenant API key

    **When to use:**
    - After mass session revocations
    - To ensure wallet lock state is consistent
    - Periodic maintenance (recommended: hourly or daily)

    **Note:** This is tenant-scoped - only affects wallets in the current tenant.
    """
    try:
        cleanup_service = get_cleanup_service()
        result = await cleanup_service.cleanup_expired_sessions(tenant_id)

        return AdminWalletSyncResponse(
            success=True,
            wallets_locked=result["wallets_locked"],
            sessions_removed_from_memory=result["sessions_removed_from_memory"],
            wallets_checked=result["wallets_checked"],
            message=f"Checked {result['wallets_checked']} wallets: "
                    f"locked {result['wallets_locked']} wallets, "
                    f"removed {result['sessions_removed_from_memory']} sessions from memory",
        )

    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to sync wallet locks: {str(e)}"
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
    tenant_id: str = Depends(require_tenant_context),
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
        admin_service = AdminSessionService()
        revoked = await admin_service.revoke_session_by_jti(jti)

        if not revoked:
            raise HTTPException(
                status_code=404,
                detail=f"Session with JTI '{jti}' not found"
            )

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
    tenant_id: str = Depends(require_tenant_context),
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
        admin_service = AdminSessionService()
        result = await admin_service.clear_all_sessions()

        return AdminClearAllResponse(
            success=True,
            cleared_memory=result["memory_cleared"],
            revoked_database=result["db_revoked"],
            message=f"Emergency: Cleared {result['memory_cleared']} sessions from memory "
                    f"and revoked {result['db_revoked']} in database",
            warning="⚠️  All users have been logged out. They must unlock their wallets again.",
        )

    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to clear sessions: {str(e)}"
        )


@router.post(
    "/sessions/purge",
    summary="Purge old revoked sessions",
    description="Permanently delete old revoked sessions from database (CORE wallets only)",
    responses={
        403: {"model": ErrorResponse, "description": "Access denied - CORE wallet required"},
        500: {"model": ErrorResponse, "description": "Server error"},
    },
)
async def purge_old_sessions(
    retention_days: int = 30,
    admin: WalletAuthContext = Depends(require_core_wallet),
    tenant_id: str = Depends(require_tenant_context),
):
    """
    Purge old revoked sessions from database.

    This endpoint:
    1. Finds all revoked sessions older than retention period
    2. Permanently DELETES them from database
    3. Helps prevent database bloat from accumulating sessions

    **Access Control:**
    - Requires CORE wallet authentication
    - Requires valid API key

    **Retention Period:**
    - Default: 30 days (revoked sessions older than 30 days are deleted)
    - Configurable via query parameter: ?retention_days=90

    **Best Practices:**
    - Keep revoked sessions for audit trail (30-90 days recommended)
    - Run periodically (weekly/monthly) to prevent bloat
    - Adjust retention_days based on compliance requirements

    **Note:**
    - Only affects REVOKED sessions (already logged out)
    - Active sessions are never purged
    - Deleted sessions cannot be recovered
    """
    try:
        admin_service = AdminSessionService()
        result = await admin_service.purge_old_revoked_sessions(retention_days=retention_days)

        return {
            "success": True,
            "purged_count": result["purged_count"],
            "retention_days": result["retention_days"],
            "cutoff_date": result["cutoff_date"].isoformat(),
            "message": f"Purged {result['purged_count']} old revoked sessions (older than {retention_days} days)"
        }

    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to purge sessions: {str(e)}"
        )


# ============================================================================
# API Key Management Endpoints
# ============================================================================


class CreateApiKeyRequest(BaseModel):
    name: str
    scopes: list[str] = ["read", "write"]
    expires_days: int | None = None


class ApiKeyResponse(BaseModel):
    api_key: str  # Only shown once!
    api_key_prefix: str
    name: str
    scopes: list[str]
    expires_at: datetime | None
    created_at: datetime


class ApiKeyListItem(BaseModel):
    api_key_prefix: str
    name: str
    is_active: bool
    scopes: list[str]
    last_used_at: datetime | None
    expires_at: datetime | None
    created_at: datetime


@router.post(
    "/api-keys",
    response_model=ApiKeyResponse,
    summary="Create API key for tenant",
    description="Generate new API key for current tenant (CORE wallet only)",
    responses={
        403: {"model": ErrorResponse, "description": "Access denied - CORE wallet required"},
        500: {"model": ErrorResponse, "description": "Server error"},
    },
)
async def create_tenant_api_key(
    request: CreateApiKeyRequest,
    core_wallet: WalletAuthContext = Depends(require_core_wallet),
    tenant_id: str = Depends(require_tenant_context),
) -> ApiKeyResponse:
    """
    Generate new API key for current tenant (CORE wallet only)

    WARNING: The API key is only shown ONCE during creation.
    Make sure to save it securely.

    **Access Control:**
    - Requires CORE wallet authentication
    - Requires valid tenant API key

    **Security:**
    - API key is scoped to current tenant only
    - Cannot create keys for other tenants
    - Key is hashed before storage

    Args:
        request: API key creation parameters
        core_wallet: Authenticated CORE wallet context
        tenant_id: Current tenant ID from API key

    Returns:
        ApiKeyResponse with the generated API key (only shown once!)
    """

    # Generate new API key
    api_key = generate_api_key()
    api_key_hash = hash_api_key(api_key)
    api_key_prefix = api_key[:8]

    # Calculate expiration
    expires_at = None
    if request.expires_days:
        expires_at = datetime.utcnow() + timedelta(days=request.expires_days)

    # Create API key record
    api_key_record = ApiKey(
        api_key_hash=api_key_hash,
        api_key_prefix=api_key_prefix,
        tenant_id=tenant_id,  # Locked to current tenant
        name=request.name,
        is_active=True,
        scopes=request.scopes,
        expires_at=expires_at,
        created_at=datetime.utcnow(),
    )
    await api_key_record.insert()

    return ApiKeyResponse(
        api_key=api_key,  # Only shown this once!
        api_key_prefix=api_key_prefix,
        name=request.name,
        scopes=request.scopes,
        expires_at=expires_at,
        created_at=api_key_record.created_at,
    )


@router.get(
    "/api-keys",
    response_model=list[ApiKeyListItem],
    summary="List tenant API keys",
    description="List all API keys for current tenant (CORE wallet only)",
    responses={
        403: {"model": ErrorResponse, "description": "Access denied - CORE wallet required"},
        500: {"model": ErrorResponse, "description": "Server error"},
    },
)
async def list_tenant_api_keys(
    core_wallet: WalletAuthContext = Depends(require_core_wallet),
    tenant_id: str = Depends(require_tenant_context),
) -> list[ApiKeyListItem]:
    """
    List all API keys for current tenant (CORE wallet only)

    Returns metadata about API keys including prefix and status,
    but does NOT return the actual API key values.

    **Access Control:**
    - Requires CORE wallet authentication
    - Requires valid tenant API key

    **Security:**
    - Only shows keys belonging to current tenant
    - API key values are never returned (only on creation)

    Args:
        core_wallet: Authenticated CORE wallet context
        tenant_id: Current tenant ID from API key

    Returns:
        List of API key metadata (no actual keys)
    """

    api_keys = await ApiKey.find(
        ApiKey.tenant_id == tenant_id
    ).to_list()

    return [
        ApiKeyListItem(
            api_key_prefix=key.api_key_prefix,
            name=key.name,
            is_active=key.is_active,
            scopes=key.scopes,
            last_used_at=key.last_used_at,
            expires_at=key.expires_at,
            created_at=key.created_at,
        )
        for key in api_keys
    ]


@router.delete(
    "/api-keys/{api_key_prefix}",
    summary="Revoke tenant API key",
    description="Revoke API key by prefix (CORE wallet only)",
    responses={
        403: {"model": ErrorResponse, "description": "Access denied - CORE wallet required"},
        404: {"model": ErrorResponse, "description": "API key not found"},
        500: {"model": ErrorResponse, "description": "Server error"},
    },
)
async def revoke_tenant_api_key(
    api_key_prefix: str = Path(..., description="First 8 characters of the API key"),
    core_wallet: WalletAuthContext = Depends(require_core_wallet),
    tenant_id: str = Depends(require_tenant_context),
):
    """
    Revoke API key by prefix (CORE wallet only)

    Soft delete: marks the API key as inactive.
    The key will no longer work for authentication.

    **Access Control:**
    - Requires CORE wallet authentication
    - Requires valid tenant API key

    **Security:**
    - Can only revoke keys belonging to current tenant
    - Cannot revoke keys from other tenants

    Args:
        api_key_prefix: First 8 characters of the API key
        core_wallet: Authenticated CORE wallet context
        tenant_id: Current tenant ID from API key

    Returns:
        Success message with revoked key prefix
    """

    # Find key belonging to current tenant
    api_key = await ApiKey.find_one(
        ApiKey.api_key_prefix == api_key_prefix,
        ApiKey.tenant_id == tenant_id  # Security: only revoke own keys
    )

    if not api_key:
        raise HTTPException(
            status_code=404,
            detail=f"API key with prefix '{api_key_prefix}' not found for this tenant"
        )

    # Soft delete: mark as inactive
    api_key.is_active = False
    await api_key.save()

    return {"message": f"API key {api_key_prefix} revoked successfully"}
