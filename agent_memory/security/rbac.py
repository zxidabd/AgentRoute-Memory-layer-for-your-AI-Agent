"""Role-Based Access Control (RBAC) and Full API Key Lifecycle Management."""

import secrets
import hashlib
import uuid
from datetime import datetime, timezone, timedelta
from enum import Enum
from typing import List, Dict, Any, Optional, Set
from pydantic import BaseModel, Field


class Role(str, Enum):
    OWNER = "owner"                  # Full control over organization, billing, and keys
    ADMIN = "admin"                  # Can create/rotate keys, manage projects, and export data
    DEVELOPER = "developer"          # Can read, write, and inspect memories
    AGENT_WORKER = "agent_worker"    # Machine key restricted solely to ingest and context


class Scope(str, Enum):
    MEMORIES_READ = "memories:read"
    MEMORIES_WRITE = "memories:write"
    MEMORIES_DELETE = "memories:delete"
    KEYS_MANAGE = "keys:manage"
    ORG_EXPORT = "org:export"
    ORG_DELETE = "org:delete"
    ANALYTICS_READ = "analytics:read"


ROLE_DEFAULT_SCOPES: Dict[Role, Set[str]] = {
    Role.OWNER: {
        Scope.MEMORIES_READ.value, Scope.MEMORIES_WRITE.value, Scope.MEMORIES_DELETE.value,
        Scope.KEYS_MANAGE.value, Scope.ORG_EXPORT.value, Scope.ORG_DELETE.value, Scope.ANALYTICS_READ.value
    },
    Role.ADMIN: {
        Scope.MEMORIES_READ.value, Scope.MEMORIES_WRITE.value, Scope.MEMORIES_DELETE.value,
        Scope.KEYS_MANAGE.value, Scope.ORG_EXPORT.value, Scope.ANALYTICS_READ.value
    },
    Role.DEVELOPER: {
        Scope.MEMORIES_READ.value, Scope.MEMORIES_WRITE.value, Scope.MEMORIES_DELETE.value,
        Scope.ANALYTICS_READ.value
    },
    Role.AGENT_WORKER: {
        Scope.MEMORIES_READ.value, Scope.MEMORIES_WRITE.value
    }
}


class PermissionDeniedException(Exception):
    """Raised when an API key attempts an unauthorized operation."""
    pass


class APIKeyMetadata(BaseModel):
    id: str
    org_id: str
    project_id: Optional[str] = None
    name: str
    key_hash: str
    key_hint: str
    role: Role
    scopes: List[str]
    is_active: bool = True
    created_at: datetime
    expires_at: Optional[datetime] = None
    last_used_at: Optional[datetime] = None


class RBACManager:
    """Manages creation, rotation, revocation, and validation of scoped API keys."""

    @staticmethod
    def generate_key(
        org_id: str,
        name: str,
        role: Role = Role.DEVELOPER,
        project_id: Optional[str] = None,
        custom_scopes: Optional[List[str]] = None,
        expires_in_days: Optional[int] = None,
        is_test: bool = False
    ) -> Dict[str, Any]:
        """
        Creates a new cryptographically secure API key with role and scopes.
        Returns plaintext key ONCE.
        """
        prefix = "mem_test_" if is_test else "mem_live_"
        raw_token = secrets.token_urlsafe(32)
        plaintext_key = f"{prefix}{raw_token}"
        key_hash = hashlib.sha256(plaintext_key.encode()).hexdigest()
        key_hint = f"{plaintext_key[:12]}...{plaintext_key[-4:]}"
        key_id = f"key_{uuid.uuid4().hex[:12]}"

        # Resolve assigned scopes
        assigned_scopes = list(ROLE_DEFAULT_SCOPES.get(role, set()))
        if custom_scopes:
            assigned_scopes = list(set(assigned_scopes).union(set(custom_scopes)))

        now = datetime.now(timezone.utc)
        expires_at = now + timedelta(days=expires_in_days) if expires_in_days else None

        metadata = APIKeyMetadata(
            id=key_id,
            org_id=org_id,
            project_id=project_id,
            name=name,
            key_hash=key_hash,
            key_hint=key_hint,
            role=role,
            scopes=assigned_scopes,
            is_active=True,
            created_at=now,
            expires_at=expires_at
        )

        return {
            "key_id": key_id,
            "api_key": plaintext_key,
            "key_hint": key_hint,
            "metadata": metadata
        }

    @staticmethod
    def verify_key(
        metadata: APIKeyMetadata, required_scope: Optional[str] = None
    ) -> bool:
        """
        Verifies that an API key is active, not expired, and possesses the required scope.
        """
        if not metadata.is_active:
            raise PermissionDeniedException("API key has been revoked.")

        now = datetime.now(timezone.utc)
        if metadata.expires_at and now > metadata.expires_at:
            raise PermissionDeniedException("API key has expired.")

        if required_scope and required_scope not in metadata.scopes:
            raise PermissionDeniedException(
                f"Missing required permission scope '{required_scope}' for role '{metadata.role.value}'."
            )

        return True
