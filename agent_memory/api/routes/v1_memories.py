"""Production v1 Memory management, async ingestion, search, and context endpoints."""

from datetime import datetime, timezone
from typing import Dict, Any, Optional, List
from fastapi import APIRouter, Depends, HTTPException, Query, status, Request
from sqlalchemy.orm import Session
from ...models.api import IngestMemoryRequest, SearchMemoryRequest
from ...models.api_schemas import (
    StandardResponse, ResponseMeta, IngestJobResponse, MemoryItem, PaginatedMemories, MemoryPatchRequest
)
from ...models.db_models import Memory, MemoryVersion, MemoryStatus, SourceType
from ...database import get_db_session, get_read_db_session
from ...security.encryption import encrypt_field, decrypt_field
from ...security.rbac import Scope
from ...queue.redis_queue import memory_queue
from ...queue.worker import worker
from ...engine.embeddings import EmbeddingService
from ...engine.ranking import MemoryRanker
from ..auth import get_current_tenant
from ...billing.plan_enforcer import PlanEnforcer
from ...billing.usage_tracker import UsageTracker
from ...billing.plans import BillableEventType
from ...cache.redis_cache import context_cache

router = APIRouter(prefix="/v1", tags=["Memories (v1)"])
embeddings = EmbeddingService()
ranker = MemoryRanker(embeddings)


@router.post(
    "/memories",
    status_code=status.HTTP_202_ACCEPTED,
    summary="Asynchronously ingest conversation turns (Production Queue)",
    description="Validates payload, scrubs PII, and enqueues to Redis background worker fleet. Returns job_id in < 10ms."
)
def ingest_memories(
    payload: IngestMemoryRequest,
    sync: bool = Query(default=False, description="Set true for immediate synchronous processing"),
    tenant_id: str = Depends(get_current_tenant),
    db: Session = Depends(get_db_session)
) -> Dict[str, Any]:
    # Enforce memory quota before accepting ingestion
    PlanEnforcer.enforce_memory_quota(db, tenant_id)

    # Record billable ingestion turn
    UsageTracker.record_event(
        db=db,
        org_id=tenant_id,
        endpoint="/v1/memories",
        event_type=BillableEventType.INGESTION_TURN,
        units_billed=1
    )

    job_payload = {
        "org_id": tenant_id,
        "project_id": getattr(payload, "project_id", None),
        "agent_id": payload.agent_id,
        "user_id": payload.user_id,
        "messages": payload.messages,
    }

    # Invalidate cached context on memory update
    context_cache.invalidate_user_context(tenant_id, payload.user_id)

    if sync:
        # Synchronous execution
        res = worker._execute_ingestion(job_payload)
        return {
            "status": "completed",
            "sync": True,
            "facts_extracted": res.get("facts_extracted", 0),
            "memory_ids": res.get("memory_ids", [])
        }

    # Enqueue to async Redis/in-memory stream
    job_id = memory_queue.enqueue(job_payload)
    return {
        "status": "accepted",
        "job_id": job_id,
        "enqueued_at": datetime.now(timezone.utc).isoformat(),
        "poll_url": f"/v1/jobs/{job_id}",
        "message": "Memory extraction job enqueued. Processing asynchronously in worker pool."
    }


@router.get(
    "/jobs/{job_id}",
    summary="Get status of an async ingestion job",
    description="Check whether background fact extraction is QUEUED, PROCESSING, COMPLETED, or DEAD_LETTER."
)
def get_job_status(job_id: str) -> Dict[str, Any]:
    status_info = memory_queue.get_job_status(job_id)
    return status_info


@router.get(
    "/memories",
    response_model=PaginatedMemories,
    summary="Cursor-based paginated memories list with filters",
    description="List active or historical memories for a user, filtered by category and status."
)
def list_memories(
    user_id: str = Query(..., description="Target end-user identifier"),
    category: Optional[str] = Query(default=None, description="Filter by category (FACT, PREFERENCE, DECISION)"),
    status: Optional[str] = Query(default=MemoryStatus.ACTIVE.value, description="Filter by status (ACTIVE, SUPERSEDED, SOFT_DELETED)"),
    limit: int = Query(default=20, ge=1, le=100),
    cursor: Optional[str] = Query(default=None, description="Cursor for pagination"),
    tenant_id: str = Depends(get_current_tenant),
    db: Session = Depends(get_db_session)
) -> PaginatedMemories:
    query = db.query(Memory).filter(Memory.org_id == tenant_id, Memory.user_id == user_id)

    if status:
        query = query.filter(Memory.status == status)
    if category:
        query = query.filter(Memory.category == category.upper())
    if cursor:
        query = query.filter(Memory.id > cursor)

    records = query.order_by(Memory.id.asc()).limit(limit + 1).all()
    has_more = len(records) > limit
    results = records[:limit]

    items = []
    for r in results:
        items.append(
            MemoryItem(
                id=r.id,
                statement=decrypt_field(r.statement),
                category=r.category,
                entity=r.entity,
                attribute=r.attribute,
                value=r.value,
                status=r.status,
                version=r.version,
                importance_score=r.importance_score,
                confidence_score=r.confidence_score,
                created_at=r.created_at.isoformat(),
                valid_from=r.valid_from.isoformat() if r.valid_from else r.created_at.isoformat(),
                valid_until=r.valid_until.isoformat() if r.valid_until else None
            )
        )

    next_cursor = results[-1].id if has_more and results else None
    return PaginatedMemories(
        memories=items,
        total_count=len(items),
        has_more=has_more,
        next_cursor=next_cursor
    )


@router.get(
    "/memories/{memory_id}",
    summary="Get single memory with audit version ledger",
    description="Inspects memory details, provenance, and historical edit versions."
)
def get_memory_detail(
    memory_id: str,
    tenant_id: str = Depends(get_current_tenant),
    db: Session = Depends(get_db_session)
) -> Dict[str, Any]:
    record = db.query(Memory).filter(Memory.id == memory_id, Memory.org_id == tenant_id).first()
    if not record:
        raise HTTPException(status_code=404, detail="Memory record not found.")

    versions = (
        db.query(MemoryVersion)
        .filter(MemoryVersion.memory_id == memory_id)
        .order_by(MemoryVersion.version_number.asc())
        .all()
    )

    return {
        "id": record.id,
        "statement": decrypt_field(record.statement),
        "category": record.category,
        "entity": record.entity,
        "attribute": record.attribute,
        "value": record.value,
        "status": record.status,
        "version": record.version,
        "importance_score": record.importance_score,
        "confidence_score": record.confidence_score,
        "superseded_by_id": record.superseded_by_id,
        "created_at": record.created_at.isoformat(),
        "versions": [
            {
                "version_number": v.version_number,
                "statement": decrypt_field(v.statement),
                "status": v.status,
                "reason": v.reason,
                "created_at": v.created_at.isoformat()
            }
            for v in versions
        ]
    }


@router.patch(
    "/memories/{memory_id}",
    summary="Manually correct or edit a memory statement",
    description="Updates memory value and writes an immutable audit record in memory_versions."
)
def patch_memory(
    memory_id: str,
    payload: MemoryPatchRequest,
    tenant_id: str = Depends(get_current_tenant),
    db: Session = Depends(get_db_session)
) -> Dict[str, Any]:
    record = db.query(Memory).filter(Memory.id == memory_id, Memory.org_id == tenant_id).first()
    if not record:
        raise HTTPException(status_code=404, detail="Memory record not found.")

    now = datetime.now(timezone.utc)
    new_version_num = record.version + 1

    if payload.statement:
        record.statement = encrypt_field(payload.statement)
        # Update embedding vector
        vec = embeddings.embed_text(payload.statement)
        record.embedding_json = str(vec) if vec else None

    if payload.importance_score is not None:
        record.importance_score = payload.importance_score

    record.version = new_version_num
    record.updated_at = now

    # Append to version audit ledger
    audit_ver = MemoryVersion(
        id=f"ver_{datetime.now().strftime('%Y%m%d%H%M%S')}_{new_version_num}",
        memory_id=record.id,
        version_number=new_version_num,
        statement=record.statement,
        status=record.status,
        reason=payload.reason or "Manual patch correction"
    )
    db.add(audit_ver)
    db.commit()

    return {
        "status": "updated",
        "memory_id": record.id,
        "new_version": new_version_num,
        "statement": decrypt_field(record.statement)
    }


@router.delete(
    "/memories/{memory_id}",
    summary="Soft-delete or permanently purge a single memory",
    description="Default: Soft-deletes memory (marked SOFT_DELETED). Pass ?purge=true for permanent database deletion."
)
def delete_single_memory(
    memory_id: str,
    purge: bool = Query(default=False, description="Set true for irreversible hard deletion"),
    tenant_id: str = Depends(get_current_tenant),
    db: Session = Depends(get_db_session)
) -> Dict[str, Any]:
    record = db.query(Memory).filter(Memory.id == memory_id, Memory.org_id == tenant_id).first()
    if not record:
        raise HTTPException(status_code=404, detail="Memory record not found.")

    if purge:
        db.delete(record)
        db.commit()
        return {"status": "purged", "memory_id": memory_id, "type": "hard_delete"}

    # Soft deletion
    record.status = MemoryStatus.SOFT_DELETED.value
    record.updated_at = datetime.now(timezone.utc)
    db.commit()
    return {"status": "soft_deleted", "memory_id": memory_id, "type": "soft_delete"}


@router.post(
    "/context",
    summary="Primary Agent Context Injection (< 30ms)",
    description="Retrieves active memories, applies Ebbinghaus decay & ranking, and clamps strictly to token budget."
)
def get_prompt_context(
    payload: SearchMemoryRequest,
    tenant_id: str = Depends(get_current_tenant),
    db: Session = Depends(get_read_db_session)
) -> Dict[str, Any]:
    # Enforce request/query quota before serving context
    PlanEnforcer.enforce_query_quota(db, tenant_id)

    # Record billable context recall event
    UsageTracker.record_event(
        db=db,
        org_id=tenant_id,
        endpoint="/v1/context",
        event_type=BillableEventType.RECALL_QUERY,
        units_billed=1
    )

    # 1. Check 60-second Redis/Local context cache
    cached = context_cache.get_cached_context(tenant_id, payload.user_id, payload.query)
    if cached:
        return cached

    # Query only ACTIVE memories
    records = (
        db.query(Memory)
        .filter(Memory.org_id == tenant_id, Memory.user_id == payload.user_id, Memory.status == MemoryStatus.ACTIVE.value)
        .all()
    )

    if not records:
        return {"user_id": payload.user_id, "context": "", "token_count": 0, "memory_count": 0}

    # Decrypt memory statements for ranking
    from ...models.memory import MemoryRecord
    mem_models = []
    for r in records:
        decrypted_stmt = decrypt_field(r.statement)
        embed = None
        if r.embedding_json:
            try:
                import ast
                embed = ast.literal_eval(r.embedding_json)
            except Exception:
                embed = embeddings.embed_text(decrypted_stmt)

        mem_models.append(
            MemoryRecord(
                id=r.id,
                tenant_id=r.org_id,
                user_id=r.user_id,
                agent_id=r.agent_id,
                statement=decrypted_stmt,
                category=r.category,
                entity=r.entity,
                attribute=r.attribute or "",
                value=r.value or "",
                importance=r.importance_score,
                access_count=r.access_count,
                is_active=(r.status == MemoryStatus.ACTIVE.value),
                created_at=r.created_at,
                embedding=embed
            )
        )

    # Rank and clamp to token budget
    ranked = ranker.rank(payload.query, mem_models, limit=payload.limit)

    # Touch accessed records in DB
    now = datetime.now(timezone.utc)
    for m, _ in ranked:
        db.query(Memory).filter(Memory.id == m.id).update(
            {"access_count": Memory.access_count + 1, "last_accessed_at": now}
        )
    db.commit()

    context_resp = ranker.build_context_string(payload.user_id, ranked, token_limit=payload.token_limit)
    response_data = {
        "user_id": payload.user_id,
        "context": context_resp.context,
        "token_count": context_resp.token_count,
        "memory_count": context_resp.memory_count
    }
    # Cache for 60 seconds
    context_cache.cache_context(tenant_id, payload.user_id, payload.query, response_data, ttl=60)
    return response_data
