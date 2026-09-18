"""API Key lifecycle management: generation, hashing, verification, revocation, and rotation."""

import secrets
import hashlib
import uuid
import json
from datetime import datetime, timezone, timedelta
from typing import Dict, Any, Optional, List, Tuple
from sqlalchemy.orm import Session
from ..models.db_models import APIKey, Project, Organization


class APIKeyService:
    """Manages project-scoped API keys with format mb_{env}_{random32}."""

    VALID_ENVS = {"dev", "staging", "prod", "test", "live"}

    @classmethod
    def generate_api_key(
        cls,
        db: Session,
        org_id: str,
        name: str,
        project_id: Optional[str] = None,
        environment: str = "dev",
        role: str = "developer",
        created_by_id: Optional[str] = None,
        expires_in_days: Optional[int] = None,
        scopes: Optional[List[str]] = None
    ) -> Dict[str, Any]:
        """
        Generates a new project-scoped API key.
        Returns the plaintext key ONCE.
        """
        env = environment.lower() if environment.lower() in cls.VALID_ENVS else "dev"
        random_part = secrets.token_urlsafe(32)
        plaintext_key = f"mb_{env}_{random_part}"

        key_hash = hashlib.sha256(plaintext_key.encode("utf-8")).hexdigest()
        key_prefix = f"mb_{env}"
        key_hint = f"mb_{env}_{random_part[:4]}...{random_part[-4:]}"
        key_id = f"key_{uuid.uuid4().hex[:12]}"

        now = datetime.now(timezone.utc)
        expires_at = now + timedelta(days=expires_in_days) if expires_in_days else None
        scopes_json = json.dumps(scopes or [])

        db_key = APIKey(
            id=key_id,
            org_id=org_id,
            project_id=project_id,
            name=name,
            key_prefix=key_prefix,
            key_hash=key_hash,
            key_hint=key_hint,
            environment=env,
            role=role.lower(),
            created_by_id=created_by_id,
            scopes_json=scopes_json,
            is_active=True,
            expires_at=expires_at,
            created_at=now,
            revoked_at=None
        )
        db.add(db_key)
        db.commit()
        db.refresh(db_key)

        return {
            "key_id": key_id,
            "api_key": plaintext_key,
            "key_hint": key_hint,
            "name": name,
            "org_id": org_id,
            "project_id": project_id,
            "environment": env,
            "role": role.lower(),
            "expires_at": expires_at.isoformat() if expires_at else None,
            "created_at": now.isoformat(),
            "message": "Copy this key now. It will never be shown in plaintext again."
        }

    @classmethod
    def verify_api_key(cls, db: Session, raw_key: str) -> Optional[APIKey]:
        """
        Validates an incoming plaintext API key against the database.
        Returns the APIKey model instance if valid and active, else None.
        """
        if not raw_key:
            return None

        # Master dev token bypass
        if raw_key == "mem_dev_master_key_123":
            key = db.query(APIKey).filter(APIKey.key_hash == "dev_master").first()
            if not key:
                key = APIKey(
                    id="key_dev_master",
                    org_id="org_default_dev",
                    name="Dev Master Key",
                    key_prefix="mem_dev",
                    key_hash="dev_master",
                    key_hint="mem_dev_master...",
                    environment="dev",
                    role="owner",
                    is_active=True
                )
            return key

        key_hash = hashlib.sha256(raw_key.encode("utf-8")).hexdigest()
        key = db.query(APIKey).filter(APIKey.key_hash == key_hash).first()

        if not key:
            return None

        if not key.is_active or key.revoked_at is not None:
            return None

        now = datetime.now(timezone.utc)
        if key.expires_at:
            exp = key.expires_at
            if exp.tzinfo is None:
                exp = exp.replace(tzinfo=timezone.utc)
            if now > exp:
                return None

        # Record last_used_at
        key.last_used_at = now
        try:
            db.commit()
        except Exception:
            db.rollback()

        return key

    @classmethod
    def revoke_api_key(cls, db: Session, key_id: str, org_id: str) -> bool:
        """Immediately deactivates and revokes an API key."""
        key = db.query(APIKey).filter(APIKey.id == key_id, APIKey.org_id == org_id).first()
        if not key:
            return False

        now = datetime.now(timezone.utc)
        key.is_active = False
        key.revoked_at = now
        db.commit()
        return True

    @classmethod
    def rotate_api_key(cls, db: Session, key_id: str, org_id: str) -> Optional[Dict[str, Any]]:
        """Revokes old key and creates a fresh key with same settings."""
        old_key = db.query(APIKey).filter(APIKey.id == key_id, APIKey.org_id == org_id).first()
        if not old_key:
            return None

        now = datetime.now(timezone.utc)
        old_key.is_active = False
        old_key.revoked_at = now
        db.commit()

        scopes = json.loads(old_key.scopes_json) if old_key.scopes_json else []

        new_key_data = cls.generate_api_key(
            db=db,
            org_id=org_id,
            name=f"{old_key.name} (Rotated)",
            project_id=old_key.project_id,
            environment=old_key.environment or "dev",
            role=old_key.role or "developer",
            created_by_id=old_key.created_by_id,
            scopes=scopes
        )
        new_key_data["revoked_key_id"] = old_key.id
        return new_key_data

    @classmethod
    def list_keys_for_project(cls, db: Session, project_id: str, org_id: str) -> List[Dict[str, Any]]:
        """Lists all keys scoped to a specific project."""
        keys = db.query(APIKey).filter(
            APIKey.project_id == project_id,
            APIKey.org_id == org_id
        ).order_by(APIKey.created_at.desc()).all()

        return [
            {
                "id": k.id,
                "name": k.name,
                "key_prefix": k.key_prefix,
                "key_hint": k.key_hint,
                "environment": k.environment,
                "role": k.role,
                "is_active": k.is_active and k.revoked_at is None,
                "created_at": k.created_at.isoformat() if k.created_at else None,
                "expires_at": k.expires_at.isoformat() if k.expires_at else None,
                "last_used_at": k.last_used_at.isoformat() if k.last_used_at else None,
                "revoked_at": k.revoked_at.isoformat() if k.revoked_at else None,
            }
            for k in keys
        ]

    @classmethod
    def list_keys_for_org(cls, db: Session, org_id: str) -> List[Dict[str, Any]]:
        """Lists all keys for an entire organization."""
        keys = db.query(APIKey).filter(
            APIKey.org_id == org_id
        ).order_by(APIKey.created_at.desc()).all()

        return [
            {
                "id": k.id,
                "name": k.name,
                "project_id": k.project_id,
                "key_prefix": k.key_prefix,
                "key_hint": k.key_hint,
                "environment": k.environment,
                "role": k.role,
                "is_active": k.is_active and k.revoked_at is None,
                "created_at": k.created_at.isoformat() if k.created_at else None,
                "expires_at": k.expires_at.isoformat() if k.expires_at else None,
                "last_used_at": k.last_used_at.isoformat() if k.last_used_at else None,
                "revoked_at": k.revoked_at.isoformat() if k.revoked_at else None,
            }
            for k in keys
        ]

