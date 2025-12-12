"""
Admin API for tenant and API key management

Protected endpoints for creating/managing tenants and their API keys.
All endpoints require admin API key authentication.
"""

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, EmailStr
from datetime import datetime, timedelta

from api.dependencies.admin import require_admin_key

router = APIRouter(prefix="/admin", tags=["admin"])


# ============================================================================
# Request/Response Models
# ============================================================================

class TenantCreate(BaseModel):
    tenant_id: str  # e.g., "acme_corp"
    tenant_name: str  # e.g., "ACME Corporation"
    admin_email: EmailStr
    plan_tier: str = "free"


class TenantResponse(BaseModel):
    tenant_id: str
    tenant_name: str
    database_name: str
    is_active: bool
    created_at: datetime


class ApiKeyCreate(BaseModel):
    name: str  # Descriptive name
    scopes: list[str] = ["read", "write"]
    expires_days: int | None = None  # Optional expiration in days


class ApiKeyResponse(BaseModel):
    api_key: str  # Only returned once on creation
    api_key_prefix: str
    tenant_id: str
    name: str
    created_at: datetime


# ============================================================================
# Tenant Management Endpoints
# ============================================================================

@router.post("/tenants", response_model=TenantResponse)
async def create_tenant(
    data: TenantCreate,
    admin_key: str = Depends(require_admin_key)
):
    """
    Create new tenant and database configuration

    This endpoint:
    1. Creates a tenant record in the admin database
    2. Registers the tenant's database name
    3. Returns tenant details

    Note: The tenant's MongoDB database URI must be configured separately
    in AWS Secrets Manager as MONGODB_URI_{TENANT_ID}.
    """
    from api.database.models import Tenant
    from api.database.multi_tenant_manager import get_multi_tenant_db_manager

    # Check if tenant already exists
    existing = await Tenant.find_one(Tenant.tenant_id == data.tenant_id)
    if existing:
        raise HTTPException(status_code=400, detail="Tenant already exists")

    # Create tenant record
    tenant = Tenant(
        tenant_id=data.tenant_id,
        tenant_name=data.tenant_name,
        database_name=f"terrasacha_{data.tenant_id}",
        admin_email=data.admin_email,
        plan_tier=data.plan_tier,
        is_active=True,
    )
    await tenant.insert()

    # Note: Database will be initialized lazily on first API request
    # Or you can initialize immediately:
    # db_manager = get_multi_tenant_db_manager()
    # await db_manager.get_tenant_database(data.tenant_id)

    return TenantResponse(
        tenant_id=tenant.tenant_id,
        tenant_name=tenant.tenant_name,
        database_name=tenant.database_name,
        is_active=tenant.is_active,
        created_at=tenant.created_at,
    )


@router.get("/tenants/{tenant_id}", response_model=TenantResponse)
async def get_tenant(
    tenant_id: str,
    admin_key: str = Depends(require_admin_key)
):
    """Get tenant details by ID"""
    from api.database.models import Tenant

    tenant = await Tenant.find_one(Tenant.tenant_id == tenant_id)
    if not tenant:
        raise HTTPException(status_code=404, detail="Tenant not found")

    return TenantResponse(
        tenant_id=tenant.tenant_id,
        tenant_name=tenant.tenant_name,
        database_name=tenant.database_name,
        is_active=tenant.is_active,
        created_at=tenant.created_at,
    )


@router.get("/tenants", response_model=list[TenantResponse])
async def list_tenants(admin_key: str = Depends(require_admin_key)):
    """List all tenants"""
    from api.database.models import Tenant

    tenants = await Tenant.find_all().to_list()

    return [
        TenantResponse(
            tenant_id=tenant.tenant_id,
            tenant_name=tenant.tenant_name,
            database_name=tenant.database_name,
            is_active=tenant.is_active,
            created_at=tenant.created_at,
        )
        for tenant in tenants
    ]


@router.patch("/tenants/{tenant_id}/activate")
async def activate_tenant(
    tenant_id: str,
    admin_key: str = Depends(require_admin_key)
):
    """Activate a tenant"""
    from api.database.models import Tenant

    tenant = await Tenant.find_one(Tenant.tenant_id == tenant_id)
    if not tenant:
        raise HTTPException(status_code=404, detail="Tenant not found")

    tenant.is_active = True
    tenant.is_suspended = False
    await tenant.save()

    return {"message": "Tenant activated", "tenant_id": tenant_id}


@router.patch("/tenants/{tenant_id}/suspend")
async def suspend_tenant(
    tenant_id: str,
    admin_key: str = Depends(require_admin_key)
):
    """Suspend a tenant (prevents API access)"""
    from api.database.models import Tenant

    tenant = await Tenant.find_one(Tenant.tenant_id == tenant_id)
    if not tenant:
        raise HTTPException(status_code=404, detail="Tenant not found")

    tenant.is_suspended = True
    await tenant.save()

    return {"message": "Tenant suspended", "tenant_id": tenant_id}


# ============================================================================
# API Key Management Endpoints
# ============================================================================

@router.post("/tenants/{tenant_id}/api-keys", response_model=ApiKeyResponse)
async def create_api_key(
    tenant_id: str,
    data: ApiKeyCreate,
    admin_key: str = Depends(require_admin_key)
):
    """
    Generate new API key for tenant

    WARNING: The API key is only shown ONCE during creation.
    Make sure to save it securely.

    Args:
        tenant_id: Tenant identifier
        data: API key creation parameters

    Returns:
        ApiKeyResponse with the generated API key (only shown once!)
    """
    from api.database.models import Tenant, ApiKey
    from api.utils.security import generate_api_key, hash_api_key

    # Verify tenant exists
    tenant = await Tenant.find_one(Tenant.tenant_id == tenant_id)
    if not tenant:
        raise HTTPException(status_code=404, detail="Tenant not found")

    # Generate API key
    api_key = generate_api_key()
    api_key_hash = hash_api_key(api_key)
    api_key_prefix = api_key[:8]

    # Calculate expiration
    expires_at = None
    if data.expires_days:
        expires_at = datetime.utcnow() + timedelta(days=data.expires_days)

    # Store API key record
    api_key_record = ApiKey(
        api_key_hash=api_key_hash,
        api_key_prefix=api_key_prefix,
        tenant_id=tenant_id,
        name=data.name,
        is_active=True,
        scopes=data.scopes,
        expires_at=expires_at,
    )
    await api_key_record.insert()

    return ApiKeyResponse(
        api_key=api_key,  # Only returned once!
        api_key_prefix=api_key_prefix,
        tenant_id=tenant_id,
        name=data.name,
        created_at=api_key_record.created_at,
    )


@router.get("/tenants/{tenant_id}/api-keys")
async def list_api_keys(
    tenant_id: str,
    admin_key: str = Depends(require_admin_key)
):
    """
    List API keys for a tenant (without showing full keys)

    Returns metadata about API keys including prefix and status,
    but does NOT return the actual API key values.
    """
    from api.database.models import Tenant, ApiKey

    # Verify tenant exists
    tenant = await Tenant.find_one(Tenant.tenant_id == tenant_id)
    if not tenant:
        raise HTTPException(status_code=404, detail="Tenant not found")

    # Get all API keys for tenant
    api_keys = await ApiKey.find(ApiKey.tenant_id == tenant_id).to_list()

    return [
        {
            "api_key_prefix": key.api_key_prefix,
            "name": key.name,
            "is_active": key.is_active,
            "scopes": key.scopes,
            "created_at": key.created_at,
            "last_used_at": key.last_used_at,
            "expires_at": key.expires_at,
        }
        for key in api_keys
    ]


@router.patch("/tenants/{tenant_id}/api-keys/{api_key_prefix}/revoke")
async def revoke_api_key(
    tenant_id: str,
    api_key_prefix: str,
    admin_key: str = Depends(require_admin_key)
):
    """
    Revoke an API key (soft delete - marks as inactive)

    This immediately disables the API key, preventing it from being used.
    The key record remains in the database for audit purposes.

    To permanently delete a revoked key, use the DELETE endpoint.

    Args:
        tenant_id: Tenant identifier
        api_key_prefix: First 8 characters of the API key
    """
    from api.database.models import ApiKey

    # Find API key by prefix and tenant
    api_key = await ApiKey.find_one(
        ApiKey.tenant_id == tenant_id,
        ApiKey.api_key_prefix == api_key_prefix
    )

    if not api_key:
        raise HTTPException(status_code=404, detail="API key not found")

    if not api_key.is_active:
        raise HTTPException(status_code=400, detail="API key is already revoked")

    # Soft delete: mark as inactive
    api_key.is_active = False
    api_key.revoked_at = datetime.utcnow()
    await api_key.save()

    return {
        "message": "API key revoked successfully",
        "api_key_prefix": api_key_prefix,
        "revoked_at": api_key.revoked_at
    }


@router.delete("/tenants/{tenant_id}/api-keys/{api_key_prefix}")
async def delete_api_key(
    tenant_id: str,
    api_key_prefix: str,
    admin_key: str = Depends(require_admin_key)
):
    """
    Permanently delete an API key from the database

    **IMPORTANT**: The API key must be revoked first before it can be deleted.
    This is a safety measure to prevent accidental deletion of active keys.

    Steps:
    1. First revoke the key: PATCH /tenants/{tenant_id}/api-keys/{api_key_prefix}/revoke
    2. Then delete the key: DELETE /tenants/{tenant_id}/api-keys/{api_key_prefix}

    Args:
        tenant_id: Tenant identifier
        api_key_prefix: First 8 characters of the API key

    Raises:
        404: API key not found
        400: API key is still active (must be revoked first)
    """
    from api.database.models import ApiKey

    # Find API key by prefix and tenant
    api_key = await ApiKey.find_one(
        ApiKey.tenant_id == tenant_id,
        ApiKey.api_key_prefix == api_key_prefix
    )

    if not api_key:
        raise HTTPException(status_code=404, detail="API key not found")

    # Check if key is revoked
    if api_key.is_active:
        raise HTTPException(
            status_code=400,
            detail="Cannot delete active API key. Please revoke it first using PATCH /tenants/{tenant_id}/api-keys/{api_key_prefix}/revoke"
        )

    # Permanently delete from database
    await api_key.delete()

    return {
        "message": "API key permanently deleted from database",
        "api_key_prefix": api_key_prefix,
        "deleted_at": datetime.utcnow()
    }
