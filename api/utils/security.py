import secrets
import hashlib
from typing import Annotated

from fastapi import HTTPException, status
from fastapi.params import Security
from fastapi.security import APIKeyHeader

from api.config import settings


api_key_header_scheme = APIKeyHeader(name="x-api-key", auto_error=False)


def generate_api_key() -> str:
    """Generate a random API key"""
    # Generate a random 32-character string using secrets.token_urlsafe()
    return secrets.token_urlsafe(32)


def hash_api_key(api_key: str) -> str:
    """
    Hash API key using SHA256

    Args:
        api_key: Plain text API key

    Returns:
        str: SHA256 hash of the API key (hex format)
    """
    return hashlib.sha256(api_key.encode()).hexdigest()


def get_api_key(api_key_header: Annotated[str | None, Security(api_key_header_scheme)]) -> str:
    """Retrieve and validate an API key from the query parameters or HTTP header.

    Args:
        api_key_query: The API key passed as a query parameter.

    Returns:
        The validated API key.

    Raises:
        HTTPException: If the API key is invalid or missing.
    """
    key = settings.admin_api_key
    if api_key_header == key:
        return api_key_header
    raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid or missing API Key")


async def get_api_key_and_tenant(
    api_key_header: Annotated[str | None, Security(api_key_header_scheme)]
) -> tuple[str, str]:
    """
    Validate API key and extract tenant_id

    Supports:
    - Admin API key (returns tenant_id="admin")
    - Tenant API keys from MongoDB

    No fallbacks - all keys must be valid.

    Args:
        api_key_header: API key from x-api-key header

    Returns:
        tuple: (api_key, tenant_id)

    Raises:
        HTTPException: If API key is invalid or missing
    """
    if not api_key_header:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing API Key"
        )

    # Check admin API key first
    if api_key_header == settings.admin_api_key:
        return (api_key_header, "admin")

    # MongoDB lookup for tenant API keys
    from api.database.models import ApiKey
    from api.database.multi_tenant_manager import get_multi_tenant_db_manager

    db_manager = get_multi_tenant_db_manager()
    if not db_manager._initialized:
        await db_manager.initialize()

    api_key_hash = hash_api_key(api_key_header)
    api_key_record = await ApiKey.find_one(ApiKey.api_key_hash == api_key_hash)

    if api_key_record and api_key_record.is_active:
        # Check expiration
        if api_key_record.expires_at:
            from datetime import datetime
            if datetime.utcnow() > api_key_record.expires_at:
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="API Key expired"
                )

        # Update last used timestamp
        from datetime import datetime
        api_key_record.last_used_at = datetime.utcnow()
        await api_key_record.save()

        return (api_key_header, api_key_record.tenant_id)

    # No fallbacks - reject invalid keys
    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Invalid or inactive API Key"
    )
