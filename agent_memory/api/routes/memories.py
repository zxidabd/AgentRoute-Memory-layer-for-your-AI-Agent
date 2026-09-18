"""Memory management, search, and context endpoints."""

from typing import Dict, Any
from fastapi import APIRouter, Depends, status
from ...models.api import (
    IngestMemoryRequest,
    SearchMemoryRequest,
    SearchResponse,
    ContextResponse,
    MemoryItemResponse,
)
from ...models.memory import MemoryRecord
from ...engine.sanitizer import sanitize_text
from ...engine.extractor import FactExtractor
from ...engine.resolver import ConflictResolver
from ...engine.embeddings import EmbeddingService
from ...engine.ranking import MemoryRanker
from ...storage.sqlite_store import SQLiteMemoryStore
from ..auth import get_current_tenant

router = APIRouter(prefix="/v1", tags=["Memories"])

# Singletons for service components
store = SQLiteMemoryStore()
extractor = FactExtractor()
embeddings = EmbeddingService()
resolver = ConflictResolver(embeddings)
ranker = MemoryRanker(embeddings)


@router.post(
    "/memories",
    status_code=status.HTTP_202_ACCEPTED,
    summary="Ingest conversation turns and extract long-term memory",
    description="Analyzes messages, scrubs PII, extracts atomic facts with Gemini 2.5 Flash, and resolves contradictions in the background."
)
def add_memories(
    payload: IngestMemoryRequest,
    tenant_id: str = Depends(get_current_tenant)
) -> Dict[str, Any]:
    # 1. PII Sanitization across messages
    sanitized_messages = []
    had_pii = False
    for m in payload.messages:
        clean_content, redacted = sanitize_text(m.get("content", ""))
        if redacted:
            had_pii = True
        sanitized_messages.append({"role": m.get("role", "user"), "content": clean_content})

    # 2. Fact Extraction
    extraction = extractor.extract(sanitized_messages)
    if not extraction.facts:
        return {
            "status": "ignored",
            "message": "No permanent facts detected (small talk or filler filtered out)",
            "facts_extracted": 0,
            "pii_redacted": had_pii
        }

    # 3. Retrieve existing active memories for conflict resolution
    existing_memories = store.get_active_memories(tenant_id, payload.user_id)
    saved_records = []

    for fact in extraction.facts:
        # Check for contradictions/supersessions
        conflicts = resolver.detect_conflicts(fact, existing_memories)

        # Generate vector embedding for semantic search
        vector = embeddings.embed_text(fact.statement)

        record = MemoryRecord(
            tenant_id=tenant_id,
            user_id=payload.user_id,
            agent_id=payload.agent_id,
            statement=fact.statement,
            category=fact.category.value,
            entity=fact.entity,
            attribute=fact.attribute,
            value=fact.value,
            importance=fact.importance,
            embedding=vector
        )
        new_id = store.add_memory(record)
        saved_records.append(record)

        # Supersede outdated memories
        for old_mem, _ in conflicts:
            store.mark_superseded(old_mem.id, new_id)

    return {
        "status": "recorded",
        "user_id": payload.user_id,
        "facts_extracted": len(saved_records),
        "facts": [r.statement for r in saved_records],
        "pii_redacted": had_pii
    }


@router.post(
    "/memories/search",
    response_model=SearchResponse,
    summary="Search relevant memories using hybrid ranking",
    description="Fast vector search + multi-factor ranking combining semantic match, recency, and importance."
)
def search_memories(
    payload: SearchMemoryRequest,
    tenant_id: str = Depends(get_current_tenant)
) -> SearchResponse:
    # 1. Fetch active memories for this tenant & user
    active_memories = store.get_active_memories(tenant_id, payload.user_id)

    # 2. Multi-factor rank
    ranked = ranker.rank(payload.query, active_memories, limit=payload.limit)

    # 3. Record access touches to reinforce memory
    items = []
    for mem, score in ranked:
        store.touch_memory(mem.id)
        items.append(
            MemoryItemResponse(
                id=mem.id,
                statement=mem.statement,
                category=mem.category,
                importance=mem.importance,
                relevance_score=round(score, 3),
                created_at=mem.created_at.isoformat()
            )
        )

    return SearchResponse(
        memories=items,
        query=payload.query,
        total_found=len(items)
    )


@router.post(
    "/context",
    response_model=ContextResponse,
    summary="Get prompt-ready context string clamped to token limit",
    description="The primary endpoint for AI agents. Injects directly into system prompts in under 35ms."
)
def get_prompt_context(
    payload: SearchMemoryRequest,
    tenant_id: str = Depends(get_current_tenant)
) -> ContextResponse:
    active_memories = store.get_active_memories(tenant_id, payload.user_id)
    ranked = ranker.rank(payload.query, active_memories, limit=payload.limit)

    # Touch accessed memories
    for mem, _ in ranked:
        store.touch_memory(mem.id)

    # Build prompt string clamped to token limit
    return ranker.build_context_string(
        user_id=payload.user_id,
        ranked_memories=ranked,
        token_limit=payload.token_limit
    )
