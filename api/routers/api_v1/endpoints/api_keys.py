"""
Self-Service API Key Management

Allows CORE wallets to manage their tenant's API keys.
CORE wallets can create, list, and revoke API keys for their tenant.
"""

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from datetime import datetime, timedelta

from api.dependencies.auth import require_core_wallet, WalletAuthContext
from api.dependencies.tenant import require_tenant_context
from api.database.models import ApiKey
from api.utils.security import generate_api_key, hash_api_key

router = APIRouter()


# ============================================================================
# Request/Response Models
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


# ============================================================================
# Self-Service API Key Endpoints (CORE Wallet Only)
# ============================================================================

@router.post("/", response_model=ApiKeyResponse)
async def create_tenant_api_key(
    request: CreateApiKeyRequest,
    core_wallet: WalletAuthContext = Depends(require_core_wallet),
    tenant_id: str = Depends(require_tenant_context),
):
    """
    Generate new API key for current tenant (CORE wallet only)

    WARNING: The API key is only shown ONCE during creation.
    Make sure to save it securely.

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


@router.get("/", response_model=list[ApiKeyListItem])
async def list_tenant_api_keys(
    core_wallet: WalletAuthContext = Depends(require_core_wallet),
    tenant_id: str = Depends(require_tenant_context),
):
    """
    List all API keys for current tenant (CORE wallet only)

    Returns metadata about API keys including prefix and status,
    but does NOT return the actual API key values.

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


@router.delete("/{api_key_prefix}")
async def revoke_tenant_api_key(
    api_key_prefix: str,
    core_wallet: WalletAuthContext = Depends(require_core_wallet),
    tenant_id: str = Depends(require_tenant_context),
):
    """
    Revoke API key by prefix (CORE wallet only)

    Soft delete: marks the API key as inactive.
    The key will no longer work for authentication.

    Security: Can only revoke keys belonging to current tenant.

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
