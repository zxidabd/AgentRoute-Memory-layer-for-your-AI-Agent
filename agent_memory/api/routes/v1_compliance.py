"""SOC 2 Compliance & Audit Trail API Endpoints."""

from typing import Dict, Any, List
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from ...database import get_db_session
from ...models.db_models import MemoryVersion, UsageEvent
from ...compliance.evidence_collector import EvidenceCollector
from ...auth.rbac_middleware import AuthContext, require_permission, AppRole
from ...security.encryption import decrypt_field

router = APIRouter(prefix="/v1", tags=["Enterprise Trust & Compliance (v1)"])


@router.get(
    "/compliance/evidence",
    summary="Collect point-in-time SOC 2 compliance evidence pack",
    description="Requires owner role. Scans database for encryption, RBAC, tenant isolation, and audit trail metrics."
)
def get_compliance_evidence(
    context: AuthContext = Depends(require_permission("billing:manage")),
    db: Session = Depends(get_db_session)
) -> Dict[str, Any]:
    collector = EvidenceCollector(db)
    return collector.generate_full_evidence_pack()


@router.get(
    "/audit/logs",
    summary="Retrieve immutable audit logs and memory versions",
    description="Auditor and Owner access to query immutable version history and operational audit logs."
)
def get_audit_logs(
    limit: int = Query(default=50, ge=1, le=200),
    context: AuthContext = Depends(require_permission("projects:read")),
    db: Session = Depends(get_db_session)
) -> Dict[str, Any]:
    # Query immutable memory versions
    versions = (
        db.query(MemoryVersion)
        .order_by(MemoryVersion.created_at.desc())
        .limit(limit)
        .all()
    )

    items = []
    for v in versions:
        items.append({
            "id": v.id,
            "memory_id": v.memory_id,
            "version_number": v.version_number,
            "statement": decrypt_field(v.statement),
            "status": v.status,
            "reason": v.reason,
            "created_at": v.created_at.isoformat() if v.created_at else None
        })

    return {
        "total_retrieved": len(items),
        "immutable_ledger": True,
        "audit_records": items
    }
