"""
FastAPI dependency for tenant context management

Extracts tenant from API key and ensures tenant database is initialized.
This dependency should be used in all API endpoints that require tenant isolation.
"""

from typing import Annotated
from fastapi import Depends, HTTPException

from api.utils.security import get_api_key_and_tenant
from api.database.tenant_context import set_current_tenant, clear_current_tenant
from api.database.multi_tenant_manager import get_multi_tenant_db_manager


async def get_tenant_context(
    api_key_and_tenant: Annotated[tuple[str, str], Depends(get_api_key_and_tenant)]
) -> str:
    """
    Extract and validate tenant from API key

    Sets tenant in thread-safe context and ensures database is initialized.
    This dependency handles:
    - API key validation
    - Tenant extraction from API key
    - Tenant validation (exists, active, not suspended)
    - Database initialization for tenant
    - Setting tenant in request context

    Args:
        api_key_and_tenant: Tuple of (api_key, tenant_id) from security layer

    Returns:
        str: tenant_id for the current request

    Raises:
        HTTPException: If tenant is invalid or database initialization fails
    """
    api_key, tenant_id = api_key_and_tenant

    # Admin key doesn't set tenant context (can access all)
    if tenant_id == "admin":
        return "admin"

    try:
        # Set tenant in context for this request
        set_current_tenant(tenant_id)

        # Ensure tenant database is initialized
        db_manager = get_multi_tenant_db_manager()
        await db_manager.get_tenant_database(tenant_id)

        return tenant_id

    except ValueError as e:
        # Tenant validation failed
        clear_current_tenant()
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        # Database initialization or other error
        clear_current_tenant()
        raise HTTPException(
            status_code=500,
            detail=f"Database initialization failed: {str(e)}"
        )


async def require_tenant_context(
    api_key_and_tenant: Annotated[tuple[str, str], Depends(get_api_key_and_tenant)]
) -> str:
    """
    Require a tenant API key (reject admin API key)

    Use this for endpoints that are tenant-specific and should NOT be
    accessible with the admin API key (e.g., wallets, sessions, transactions).

    Args:
        api_key_and_tenant: Tuple of (api_key, tenant_id) from security layer

    Returns:
        str: tenant_id for the current request

    Raises:
        HTTPException: If admin API key is used or tenant is invalid
    """
    api_key, tenant_id = api_key_and_tenant

    # Reject admin API key
    if tenant_id == "admin":
        raise HTTPException(
            status_code=403,
            detail="This endpoint requires a tenant API key. Admin API key cannot be used for tenant-specific resources."
        )

    try:
        # Set tenant in context for this request
        set_current_tenant(tenant_id)

        # Ensure tenant database is initialized
        db_manager = get_multi_tenant_db_manager()
        await db_manager.get_tenant_database(tenant_id)

        return tenant_id

    except ValueError as e:
        # Tenant validation failed
        clear_current_tenant()
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        # Database initialization or other error
        clear_current_tenant()
        raise HTTPException(
            status_code=500,
            detail=f"Database initialization failed: {str(e)}"
        )
