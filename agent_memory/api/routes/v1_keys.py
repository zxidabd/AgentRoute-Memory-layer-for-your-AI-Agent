"""API Key lifecycle management routes: create, rotate, revoke, expire, and list."""

import json
from datetime import datetime, timezone
from typing import Dict, Any, List, Optional
from pydantic import BaseModel, Field
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from ...models.db_models import APIKey
from ...database import get_db_session
from ...security.rbac import RBACManager, Role, Scope
from ..auth import get_current_tenant

router = APIRouter(prefix="/v1/keys", tags=["API Keys (v1)"])


class KeyCreatePayload(BaseModel):
    name: str = Field(..., description="Label for key (e.g. 'Customer Support Bot')")
    role: Role = Field(default=Role.DEVELOPER, description="Assigned RBAC role")
    project_id: Optional[str] = Field(default=None, description="Optional project scope")
    custom_scopes: Optional[List[str]] = Field(default=None, description="Custom permission overrides")
    expires_in_days: Optional[int] = Field(default=None, description="Days until automatic expiration")
    is_test: bool = Field(default=False, description="Set true for sandbox test key")


@router.post(
    "",
    summary="Create a new scoped API key",
    description="Generates a cryptographically secure API key with RBAC role. Plaintext key is returned ONCE."
)
def create_key(
    payload: KeyCreatePayload,
    tenant_id: str = Depends(get_current_tenant),
    db: Session = Depends(get_db_session)
) -> Dict[str, Any]:
    generated = RBACManager.generate_key(
        org_id=tenant_id,
        name=payload.name,
        role=payload.role,
        project_id=payload.project_id,
        custom_scopes=payload.custom_scopes,
        expires_in_days=payload.expires_in_days,
        is_test=payload.is_test
    )
    meta = generated["metadata"]

    db_key = APIKey(
        id=meta.id,
        org_id=meta.org_id,
        project_id=meta.project_id,
        name=meta.name,
        key_hash=meta.key_hash,
        key_hint=meta.key_hint,
        role=meta.role.value,
        scopes_json=json.dumps(meta.scopes),
        is_active=True,
        expires_at=meta.expires_at,
        created_at=meta.created_at
    )
    db.add(db_key)
    db.commit()

    return {
        "key_id": meta.id,
        "api_key": generated["api_key"],
        "key_hint": meta.key_hint,
        "role": meta.role.value,
        "scopes": meta.scopes,
        "expires_at": meta.expires_at.isoformat() if meta.expires_at else None,
        "message": "Copy this key now. It will never be shown in plaintext again."
    }


@router.post(
    "/{key_id}/rotate",
    summary="Rotate an existing API key",
    description="Revokes the old API key and generates a new active key with the same role and scopes."
)
def rotate_key(
    key_id: str,
    tenant_id: str = Depends(get_current_tenant),
    db: Session = Depends(get_db_session)
) -> Dict[str, Any]:
    old_key = db.query(APIKey).filter(APIKey.id == key_id, APIKey.org_id == tenant_id).first()
    if not old_key:
        raise HTTPException(status_code=404, detail="API key not found.")

    # Revoke old key
    old_key.is_active = False

    # Generate replacement key
    scopes = json.loads(old_key.scopes_json) if old_key.scopes_json else []
    generated = RBACManager.generate_key(
        org_id=tenant_id,
        name=f"{old_key.name} (Rotated)",
        role=Role(old_key.role),
        project_id=old_key.project_id,
        custom_scopes=scopes
    )
    meta = generated["metadata"]

    new_db_key = APIKey(
        id=meta.id,
        org_id=meta.org_id,
        project_id=meta.project_id,
        name=meta.name,
        key_hash=meta.key_hash,
        key_hint=meta.key_hint,
        role=meta.role.value,
        scopes_json=json.dumps(meta.scopes),
        is_active=True,
        created_at=meta.created_at
    )
    db.add(new_db_key)
    db.commit()

    return {
        "status": "rotated",
        "revoked_key_id": old_key.id,
        "new_key_id": meta.id,
        "new_api_key": generated["api_key"],
        "new_key_hint": meta.key_hint
    }


@router.delete(
    "/{key_id}",
    summary="Revoke an API key",
    description="Immediately deactivates the API key. Subsequent requests using this key will be rejected."
)
def revoke_key(
    key_id: str,
    tenant_id: str = Depends(get_current_tenant),
    db: Session = Depends(get_db_session)
) -> Dict[str, Any]:
    key = db.query(APIKey).filter(APIKey.id == key_id, APIKey.org_id == tenant_id).first()
    if not key:
        raise HTTPException(status_code=404, detail="API key not found.")

    key.is_active = False
    db.commit()
    return {"status": "revoked", "key_id": key.id, "key_hint": key.key_hint}


@router.get(
    "",
    summary="List active and revoked API keys",
    description="Lists key hints and metadata. Raw secret tokens are never stored or displayed."
)
def list_keys(
    tenant_id: str = Depends(get_current_tenant),
    db: Session = Depends(get_db_session)
) -> List[Dict[str, Any]]:
    keys = db.query(APIKey).filter(APIKey.org_id == tenant_id).order_by(APIKey.created_at.desc()).all()
    return [
        {
            "id": k.id,
            "name": k.name,
            "key_hint": k.key_hint,
            "role": k.role,
            "is_active": k.is_active,
            "expires_at": k.expires_at.isoformat() if k.expires_at else None,
            "created_at": k.created_at.isoformat(),
            "last_used_at": k.last_used_at.isoformat() if k.last_used_at else None
        }
        for k in keys
    ]
