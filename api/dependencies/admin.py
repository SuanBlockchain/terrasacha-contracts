"""
Admin Authentication

Protects administrative endpoints that manage tenants and API keys.
Only requests with valid ADMIN_API_KEY can access these endpoints.
"""

from typing import Annotated
from fastapi import Depends, HTTPException, status
from api.utils.security import get_api_key_and_tenant


async def require_admin_key(
    api_key_and_tenant: Annotated[tuple[str, str], Depends(get_api_key_and_tenant)]
) -> str:
    """
    Require admin API key for endpoint access

    Args:
        api_key_and_tenant: Tuple of (api_key, tenant_id) from authentication

    Returns:
        str: The admin API key if valid

    Raises:
        HTTPException: 403 Forbidden if not admin key
    """
    api_key, tenant_id = api_key_and_tenant

    if tenant_id != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin access required. This endpoint requires an admin API key."
        )

    return api_key
