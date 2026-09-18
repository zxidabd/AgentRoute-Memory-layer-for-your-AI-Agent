"""Auth & RBAC package for Step 2 Multi-Tenant Team Workspaces."""

from .api_key_service import APIKeyService
from .clerk_service import ClerkService
from .rbac_middleware import (
    AppRole,
    AuthContext,
    ROLE_PERMISSIONS,
    get_auth_context,
    require_permission,
    check_last_owner_guard
)

__all__ = [
    "APIKeyService",
    "ClerkService",
    "AppRole",
    "AuthContext",
    "ROLE_PERMISSIONS",
    "get_auth_context",
    "require_permission",
    "check_last_owner_guard",
]
