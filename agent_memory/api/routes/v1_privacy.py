"""Data Privacy, GDPR Right-to-be-Forgotten, Data Export, and Retention Policies."""

from datetime import datetime, timezone
from typing import Dict, Any, List
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from ...models.db_models import Memory, MemoryVersion, MemoryStatus
from ...database import get_db_session
from ...security.encryption import decrypt_field
from ..auth import get_current_tenant

router = APIRouter(prefix="/v1", tags=["Privacy & Governance (v1)"])


@router.delete(
    "/users/{user_id}",
    summary="GDPR Right to be Forgotten - Cascading memory purge",
    description="Permanently deletes all memories and version audit logs for a user across all agents."
)
@router.delete("/users/{user_id}/memories", include_in_schema=False)
def purge_user_data(
    user_id: str,
    tenant_id: str = Depends(get_current_tenant),
    db: Session = Depends(get_db_session)
) -> Dict[str, Any]:
    # Find all memories for this user
    user_memories = db.query(Memory).filter(Memory.org_id == tenant_id, Memory.user_id == user_id).all()
    count = len(user_memories)

    db.info["gdpr_purge_authorized"] = True
    for mem in user_memories:
        # Cascade delete is handled by ORM / FK, but explicitly clean up
        db.delete(mem)

    db.commit()
    return {
        "status": "purged",
        "user_id": user_id,
        "memories_deleted": count,
        "message": f"All memory records and audit logs permanently wiped for user {user_id}."
    }


@router.get(
    "/export",
    summary="Complete compliance data export",
    description="Exports all memories and audit history for this organization in compliant JSON format."
)
def export_tenant_data(
    tenant_id: str = Depends(get_current_tenant),
    db: Session = Depends(get_db_session)
) -> Dict[str, Any]:
    memories = db.query(Memory).filter(Memory.org_id == tenant_id).all()
    exported = []

    for m in memories:
        exported.append({
            "id": m.id,
            "user_id": m.user_id,
            "agent_id": m.agent_id,
            "statement": decrypt_field(m.statement),
            "category": m.category,
            "entity": m.entity,
            "attribute": m.attribute,
            "value": m.value,
            "status": m.status,
            "version": m.version,
            "created_at": m.created_at.isoformat() if m.created_at else None,
            "valid_from": m.valid_from.isoformat() if m.valid_from else None,
            "valid_until": m.valid_until.isoformat() if m.valid_until else None
        })

    return {
        "org_id": tenant_id,
        "exported_at": datetime.now(timezone.utc).isoformat(),
        "total_records": len(exported),
        "data": exported
    }


@router.post(
    "/retention/cleanup",
    summary="Trigger automated TTL retention sweep",
    description="Sweeps database and marks memories past their valid_until window as EXPIRED."
)
def sweep_retention(
    tenant_id: str = Depends(get_current_tenant),
    db: Session = Depends(get_db_session)
) -> Dict[str, Any]:
    now = datetime.now(timezone.utc)
    expired_records = (
        db.query(Memory)
        .filter(
            Memory.org_id == tenant_id,
            Memory.status == MemoryStatus.ACTIVE.value,
            Memory.valid_until != None,
            Memory.valid_until < now
        )
        .all()
    )

    for rec in expired_records:
        rec.status = MemoryStatus.EXPIRED.value
        rec.updated_at = now

    db.commit()
    return {
        "status": "sweep_completed",
        "expired_count": len(expired_records),
        "timestamp": now.isoformat()
    }
