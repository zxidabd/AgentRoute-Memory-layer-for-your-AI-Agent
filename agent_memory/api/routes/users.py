"""User profile and GDPR compliance routes."""

from typing import Dict, Any, List
from fastapi import APIRouter, Depends, HTTPException
from ...storage.sqlite_store import SQLiteMemoryStore
from ..auth import get_current_tenant

router = APIRouter(prefix="/v1/users", tags=["Users & Compliance"])
store = SQLiteMemoryStore()


@router.get(
    "/{user_id}/profile",
    summary="Get permanent synthesized profile for a user",
    description="Returns all active facts, preferences, and constraints for a given user."
)
def get_user_profile(
    user_id: str,
    tenant_id: str = Depends(get_current_tenant)
) -> Dict[str, Any]:
    active_memories = store.get_active_memories(tenant_id, user_id)
    
    preferences = [m.statement for m in active_memories if m.category == "PREFERENCE"]
    facts = [m.statement for m in active_memories if m.category == "FACT"]
    decisions = [m.statement for m in active_memories if m.category == "DECISION"]
    constraints = [m.statement for m in active_memories if m.category == "CONSTRAINT"]

    return {
        "user_id": user_id,
        "total_active_memories": len(active_memories),
        "preferences": preferences,
        "facts": facts,
        "decisions": decisions,
        "constraints": constraints,
        "all_statements": [m.statement for m in active_memories]
    }


@router.delete(
    "/{user_id}",
    summary="GDPR Right to be Forgotten - Wipe user memory",
    description="Permanently deletes all memories for a user across all agents in this tenant."
)
def delete_user_memories(
    user_id: str,
    tenant_id: str = Depends(get_current_tenant)
) -> Dict[str, Any]:
    deleted_count = store.delete_user_memories(tenant_id, user_id)
    return {
        "status": "deleted",
        "user_id": user_id,
        "memories_deleted": deleted_count,
        "message": f"Successfully wiped all memory records for user {user_id}."
    }
