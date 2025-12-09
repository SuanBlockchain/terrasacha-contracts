"""
Thread-safe tenant context management using ContextVars

Stores the current tenant_id for the active request without using global state.
This ensures proper isolation in async environments where multiple requests
are handled concurrently.
"""

from contextvars import ContextVar
from typing import Optional

# Thread-safe context variable for current tenant
_current_tenant: ContextVar[Optional[str]] = ContextVar('current_tenant', default=None)


def get_current_tenant() -> Optional[str]:
    """
    Get current tenant ID from context

    Returns:
        Optional[str]: Current tenant_id or None if not set
    """
    return _current_tenant.get()


def set_current_tenant(tenant_id: str) -> None:
    """
    Set current tenant ID in context

    Args:
        tenant_id: Tenant identifier to set in context
    """
    _current_tenant.set(tenant_id)


def clear_current_tenant() -> None:
    """Clear current tenant ID from context"""
    _current_tenant.set(None)
