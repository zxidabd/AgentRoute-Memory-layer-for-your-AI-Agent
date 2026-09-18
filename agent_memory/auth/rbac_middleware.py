"""Application-level Role-Based Access Control (RBAC) middleware, permission matrices, and guards."""

from enum import Enum
from typing import Optional, Set, Dict, List, Callable
from fastapi import Request, HTTPException, Security, Depends, Header
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy.orm import Session
from ..database import get_db_session
from ..models.db_models import Membership, Organization, APIKey
from .api_key_service import APIKeyService
from ..config import settings

security_scheme = HTTPBearer(auto_error=False)


class AppRole(str, Enum):
    OWNER = "owner"
    DEVELOPER = "developer"
    VIEWER = "viewer"


# Exact Action Matrix for Multi-Tenant Workspaces
ROLE_PERMISSIONS: Dict[str, Set[str]] = {
    AppRole.OWNER.value: {
        "memories:read",
        "memories:write",
        "memories:delete",
        "projects:read",
        "projects:manage",
        "keys:read",
        "keys:manage",
        "team:read",
        "team:manage",
        "billing:read",
        "billing:manage",
        "org:delete"
    },
    AppRole.DEVELOPER.value: {
        "memories:read",
        "memories:write",
        "memories:delete",
        "projects:read",
        "projects:manage",
        "keys:read",
        "keys:manage",
        "team:read",
        "billing:read",
    },
    AppRole.VIEWER.value: {
        "memories:read",
        "projects:read",
        "keys:read",
        "team:read",
        "billing:read",
    }
}


class AuthContext:
    """Carries verified identity, tenancy, and permission context for a request."""

    def __init__(
        self,
        org_id: str,
        role: str,
        auth_type: str = "api_key",
        project_id: Optional[str] = None,
        environment: str = "dev",
        user_id: Optional[str] = None,
        api_key_id: Optional[str] = None
    ):
        self.org_id = org_id
        self.role = role.lower()
        self.auth_type = auth_type
        self.project_id = project_id
        self.environment = environment
        self.user_id = user_id
        self.api_key_id = api_key_id

    def has_permission(self, action: str) -> bool:
        if settings.rbac_emergency_bypass:
            return True
        allowed = ROLE_PERMISSIONS.get(self.role, set())
        return action in allowed


def check_last_owner_guard(db: Session, org_id: str, member_id: str, action: str = "remove") -> None:
    """
    Enforces that an organization must never be left without an owner.
    Blocks removing or demoting the final Owner.
    """
    member = db.query(Membership).filter(
        Membership.id == member_id,
        Membership.org_id == org_id
    ).first()

    if not member:
        raise HTTPException(status_code=404, detail="Member not found in organization.")

    if member.role == AppRole.OWNER.value:
        owner_count = db.query(Membership).filter(
            Membership.org_id == org_id,
            Membership.role == AppRole.OWNER.value
        ).count()

        if owner_count <= 1:
            if action == "demote":
                raise HTTPException(
                    status_code=400,
                    detail="Cannot demote the last owner of the organization."
                )
            else:
                raise HTTPException(
                    status_code=400,
                    detail="Cannot remove the last owner of the organization."
                )


def get_auth_context(
    credentials: Optional[HTTPAuthorizationCredentials] = Security(security_scheme),
    x_api_key: Optional[str] = Header(None, alias="x-api-key"),
    x_clerk_user_id: Optional[str] = Header(None, alias="x-clerk-user-id"),
    x_org_id: Optional[str] = Header(None, alias="x-org-id"),
    db: Session = Depends(get_db_session)
) -> AuthContext:
    """
    Unified Dependency: resolves caller context from API Key or Clerk Session headers.
    """
    token = None
    if credentials and credentials.credentials:
        token = credentials.credentials.strip()
    elif x_api_key:
        token = x_api_key.strip()

    # 1. API Key Authentication
    if token:
        # Dev master key check
        if token == "mem_dev_master_key_123":
            return AuthContext(
                org_id="org_default_dev",
                role=AppRole.OWNER.value,
                auth_type="master",
                environment="dev"
            )

        api_key = APIKeyService.verify_api_key(db, token)
        if api_key:
            return AuthContext(
                org_id=api_key.org_id,
                role=api_key.role or AppRole.DEVELOPER.value,
                auth_type="api_key",
                project_id=api_key.project_id,
                environment=api_key.environment or "dev",
                api_key_id=api_key.id
            )

        raise HTTPException(
            status_code=401,
            detail="Invalid, expired, or revoked API key."
        )

    # 2. Clerk User / Session Authentication via headers
    if x_clerk_user_id and x_org_id:
        # Check membership
        membership = db.query(Membership).filter(
            Membership.org_id == x_org_id,
            Membership.clerk_user_id == x_clerk_user_id
        ).first()

        if not membership:
            raise HTTPException(
                status_code=403,
                detail="User is not an active member of this organization."
            )

        return AuthContext(
            org_id=x_org_id,
            role=membership.role,
            auth_type="clerk",
            user_id=x_clerk_user_id
        )

    # 3. Emergency Break-Glass Bypass
    if settings.rbac_emergency_bypass:
        target_org = x_org_id or "org_default_dev"
        return AuthContext(
            org_id=target_org,
            role=AppRole.OWNER.value,
            auth_type="emergency_bypass"
        )

    raise HTTPException(
        status_code=401,
        detail="Authentication required. Provide 'Authorization: Bearer mb_...' or Clerk headers."
    )


def require_permission(action: str) -> Callable[[AuthContext], AuthContext]:
    """
    Returns a FastAPI dependency that verifies whether caller has permission for action.
    """
    def _dependency(context: AuthContext = Depends(get_auth_context)) -> AuthContext:
        if not context.has_permission(action):
            raise HTTPException(
                status_code=403,
                detail=f"Role '{context.role}' does not have permission to perform '{action}'."
            )
        return context

    return _dependency
