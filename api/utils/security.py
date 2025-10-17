import secrets

from fastapi import HTTPException, status
from fastapi.params import Security
from fastapi.security import APIKeyHeader

from api.config import settings


api_key_header = APIKeyHeader(name="x-api-key", auto_error=False)


def generate_api_key():
    # Generate a random 32-character string using secrets.token_urlsafe()
    return secrets.token_urlsafe(32)


def get_api_key(api_key_header: str = Security(api_key_header)) -> str:
    """Retrieve and validate an API key from the query parameters or HTTP header.

    Args:
        api_key_query: The API key passed as a query parameter.

    Returns:
        The validated API key.

    Raises:
        HTTPException: If the API key is invalid or missing.
    """
    key = settings.api_key_dev
    if api_key_header == key:
        return api_key_header
    raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid or missing API Key")
