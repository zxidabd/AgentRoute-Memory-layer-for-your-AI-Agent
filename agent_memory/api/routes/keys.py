"""API Key generation and management endpoints for business owners."""

from typing import Dict, Any, List
from pydantic import BaseModel, Field
from fastapi import APIRouter, Depends
from ...storage.sqlite_store import SQLiteMemoryStore
from ..auth import auth_manager, get_current_tenant

router = APIRouter(prefix="/v1/keys", tags=["API Keys"])
store = SQLiteMemoryStore()


class CreateKeyRequest(BaseModel):
    org_id: str = Field(..., description="Organization ID (e.g. 'org_acme_ai')")
    name: str = Field(..., description="Key label (e.g. 'Production Support Bot')")
    is_test: bool = Field(default=False, description="Set true for sandbox test key (mem_test_...)")


@router.post(
    "",
    summary="Generate a new API key for a business owner",
    description="Creates a secure random API key, hashes it with SHA-256, and returns the plaintext key ONCE."
)
def create_key(payload: CreateKeyRequest) -> Dict[str, Any]:
    return auth_manager.generate_api_key(
        org_id=payload.org_id,
        name=payload.name,
        is_test=payload.is_test
    )


@router.get(
    "",
    summary="List active API keys for the current organization",
    description="Returns key hints and creation dates. Plaintext keys are never stored or returned."
)
def list_keys(tenant_id: str = Depends(get_current_tenant)) -> List[Dict[str, Any]]:
    return store.list_api_keys(org_id=tenant_id)
