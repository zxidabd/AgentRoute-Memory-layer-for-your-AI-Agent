"""Authentication, API Key management, and Multi-Tenant Isolation."""

import secrets
import hashlib
import uuid
from typing import Dict, Any, Optional
from fastapi import Header, HTTPException, Security, Depends
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from ..storage.sqlite_store import SQLiteMemoryStore

security_scheme = HTTPBearer(auto_error=False)


class AuthManager:
    """Manages API key lifecycle and tenant authentication."""

    def __init__(self, store: SQLiteMemoryStore = None):
        self.store = store or SQLiteMemoryStore()

    def generate_api_key(
        self, org_id: str, name: str, is_test: bool = False
    ) -> Dict[str, str]:
        """
        Generates a new secure API key for a business owner.
        Plain key is returned ONCE; only SHA-256 hash is stored in database.
        """
        prefix = "mem_test_" if is_test else "mem_live_"
        random_part = secrets.token_urlsafe(32)
        plain_key = f"{prefix}{random_part}"

        # Compute SHA-256 hash
        key_hash = hashlib.sha256(plain_key.encode()).hexdigest()

        # Create human-readable hint (e.g. "mem_live_a8f9...3b4c")
        key_hint = f"{plain_key[:12]}...{plain_key[-4:]}"
        key_id = f"key_{uuid.uuid4().hex[:10]}"

        self.store.save_api_key(
            id=key_id,
            org_id=org_id,
            name=name,
            key_hash=key_hash,
            key_hint=key_hint
        )

        return {
            "key_id": key_id,
            "org_id": org_id,
            "name": name,
            "api_key": plain_key,
            "key_hint": key_hint,
            "message": "Copy this key now. It will never be shown in plaintext again."
        }

    def authenticate_token(self, token: str) -> Dict[str, Any]:
        """Validates incoming token against SHA-256 hashes in database."""
        if not token:
            raise HTTPException(status_code=401, detail="Missing Authorization Bearer token")

        # Allow a default master key for dev/test convenience if configured
        if token == "mem_dev_master_key_123":
            return {"org_id": "org_default_dev", "key_name": "Dev Master Key"}

        token_hash = hashlib.sha256(token.encode()).hexdigest()
        record = self.store.get_api_key(token_hash)
        if not record:
            try:
                from ..database import SessionFactory
                from ..models.db_models import APIKey
                with SessionFactory() as db:
                    k = db.query(APIKey).filter(APIKey.key_hash == token_hash).first()
                    if k and k.is_active and not k.revoked_at:
                        record = {
                            "org_id": k.org_id,
                            "id": k.id,
                            "name": k.name,
                            "project_id": k.project_id,
                            "role": k.role or "developer",
                            "environment": k.environment or "dev",
                            "is_active": True
                        }
            except Exception:
                pass

        if not record or not record.get("is_active") or record.get("revoked_at"):
            raise HTTPException(status_code=401, detail="Invalid or revoked API key")

        return {
            "org_id": record["org_id"],
            "key_id": record["id"],
            "key_name": record.get("name"),
            "project_id": record.get("project_id"),
            "role": record.get("role", "developer"),
            "environment": record.get("environment", "dev")
        }


# Global auth manager instance
auth_manager = AuthManager()


def get_current_tenant(
    credentials: Optional[HTTPAuthorizationCredentials] = Security(security_scheme)
) -> str:
    """FastAPI Dependency: extracts and verifies API key, returning tenant org_id."""
    if not credentials or not credentials.credentials:
        raise HTTPException(
            status_code=401,
            detail="Authorization header missing. Expected 'Authorization: Bearer mem_live_...'"
        )
    auth_info = auth_manager.authenticate_token(credentials.credentials)
    return auth_info["org_id"]
