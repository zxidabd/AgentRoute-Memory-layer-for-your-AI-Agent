"""Background worker fleet with exponential backoff, DLQ handling, and transactional database writes."""

import time
import random
import uuid
from datetime import datetime, timezone
from typing import Dict, Any, Optional
from .redis_queue import MemoryQueue, JobStatus, memory_queue
from ..config import settings
from ..security.encryption import encrypt_field
from ..engine.sanitizer import sanitize_text
from ..engine.extractor import FactExtractor
from ..engine.resolver import ConflictResolver
from ..engine.embeddings import EmbeddingService
from ..database import get_db
from ..models.db_models import Memory, MemoryVersion, MemoryStatus, SourceType, UsageEvent


class MemoryWorker:
    """Processes asynchronous memory ingestion jobs with resilient retry policies and DLQ."""

    def __init__(
        self,
        queue: MemoryQueue = None,
        extractor: FactExtractor = None,
        resolver: ConflictResolver = None,
        embeddings: EmbeddingService = None,
    ):
        self.queue = queue or memory_queue
        self.extractor = extractor or FactExtractor()
        self.embeddings = embeddings or EmbeddingService()
        self.resolver = resolver or ConflictResolver(self.embeddings)
        self.max_retries = settings.max_worker_retries

    def process_one_job(self) -> Optional[Dict[str, Any]]:
        """Pulls and executes a single job from the queue. Useful for testing and turn-by-turn processing."""
        envelope = self.queue.dequeue(timeout_sec=1)
        if not envelope:
            return None

        job_id = envelope["job_id"]
        payload = envelope["payload"]
        retry_count = envelope.get("retry_count", 0)

        try:
            start_time = time.time()
            result = self._execute_ingestion(payload)
            elapsed_ms = (time.time() - start_time) * 1000.0

            # Record usage metering event
            self._record_usage_event(payload, elapsed_ms, facts_count=len(result.get("facts", [])))

            # Mark job complete
            self.queue.mark_completed(job_id, result)
            return {"job_id": job_id, "status": "COMPLETED", "result": result}

        except Exception as exc:
            retry_count += 1
            envelope["retry_count"] = retry_count

            if retry_count < self.max_retries:
                # Exponential backoff with jitter
                backoff_sec = min((2 ** retry_count) * 0.1, 5.0) + random.uniform(0.01, 0.05)
                time.sleep(backoff_sec)
                # Re-queue existing envelope for retry
                self.queue.re_enqueue(envelope)
                return {"job_id": job_id, "status": "RETRYING", "error": str(exc), "retry": retry_count}
            else:
                # Exceeded retries -> Route to Dead Letter Queue
                self.queue.send_to_dlq(envelope, error_msg=str(exc))
                return {"job_id": job_id, "status": "DEAD_LETTER", "error": str(exc)}

    def _execute_ingestion(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        """Core transactional memory extraction and database persistence."""
        org_id = payload["org_id"]
        project_id = payload.get("project_id")
        agent_id = payload.get("agent_id")
        user_id = payload["user_id"]
        raw_messages = payload["messages"]

        # 1. PII Scrubbing
        sanitized_messages = []
        for m in raw_messages:
            clean_content, _ = sanitize_text(m.get("content", ""))
            sanitized_messages.append({"role": m.get("role", "user"), "content": clean_content})

        # 2. Fact Extraction
        extraction = self.extractor.extract(sanitized_messages)
        if not extraction.facts:
            return {"facts_extracted": 0, "status": "ignored"}

        # 3. Database Persistence with Conflict Resolution
        saved_memory_ids = []
        now = datetime.now(timezone.utc)

        with get_db() as db:
            # Query existing active memories for this tenant & user
            existing_records = (
                db.query(Memory)
                .filter(Memory.org_id == org_id, Memory.user_id == user_id, Memory.status == MemoryStatus.ACTIVE.value)
                .all()
            )

            for fact in extraction.facts:
                new_mem_id = f"mem_{uuid.uuid4().hex[:12]}"

                # Conflict detection
                conflicts = self._check_conflicts(fact, existing_records)

                # Generate vector embedding
                vector = self.embeddings.embed_text(fact.statement)
                vector_json = str(vector) if vector else None

                # Field-level AES-256 encryption for the memory statement
                encrypted_statement = encrypt_field(fact.statement)

                new_memory = Memory(
                    id=new_mem_id,
                    org_id=org_id,
                    project_id=project_id,
                    agent_id=agent_id,
                    user_id=user_id,
                    statement=encrypted_statement,
                    category=fact.category.value,
                    entity=fact.entity,
                    attribute=fact.attribute,
                    value=fact.value,
                    status=MemoryStatus.ACTIVE.value,
                    version=1,
                    importance_score=fact.importance,
                    confidence_score=0.92,
                    created_at=now,
                    updated_at=now,
                    embedding_json=vector_json,
                    source_type=SourceType.DIRECT_USER.value
                )
                db.add(new_memory)
                saved_memory_ids.append(new_mem_id)

                # Audit ledger version record
                initial_version = MemoryVersion(
                    id=f"ver_{uuid.uuid4().hex[:10]}",
                    memory_id=new_mem_id,
                    version_number=1,
                    statement=encrypted_statement,
                    status=MemoryStatus.ACTIVE.value,
                    reason="Initial creation"
                )
                db.add(initial_version)

                # Mark superseded memories
                for old_mem in conflicts:
                    old_mem.status = MemoryStatus.SUPERSEDED.value
                    old_mem.superseded_by_id = new_mem_id
                    old_mem.updated_at = now

                    # Audit version for supersession
                    supersede_version = MemoryVersion(
                        id=f"ver_{uuid.uuid4().hex[:10]}",
                        memory_id=old_mem.id,
                        version_number=old_mem.version + 1,
                        statement=old_mem.statement,
                        status=MemoryStatus.SUPERSEDED.value,
                        superseded_by_id=new_mem_id,
                        reason=f"Superseded by {new_mem_id}"
                    )
                    db.add(supersede_version)

        return {
            "facts_extracted": len(saved_memory_ids),
            "memory_ids": saved_memory_ids,
            "status": "recorded"
        }

    def _check_conflicts(self, new_fact, existing_records):
        """Helper to find conflicting active records."""
        conflicts = []
        for old in existing_records:
            if (
                new_fact.entity
                and new_fact.attribute
                and old.entity.lower() == new_fact.entity.lower()
                and (old.attribute or "").lower() == new_fact.attribute.lower()
                and (old.value or "").lower() != new_fact.value.lower()
            ):
                conflicts.append(old)
        return conflicts

    def _record_usage_event(self, payload: Dict[str, Any], elapsed_ms: float, facts_count: int):
        """Records metering event for billing and usage quotas."""
        try:
            with get_db() as db:
                event = UsageEvent(
                    id=f"use_{uuid.uuid4().hex[:12]}",
                    org_id=payload["org_id"],
                    project_id=payload.get("project_id"),
                    endpoint="/v1/memories (worker)",
                    input_tokens=250,
                    output_tokens=50 * facts_count,
                    estimated_cost_usd=0.000045 * max(1, facts_count),
                    latency_ms=elapsed_ms
                )
                db.add(event)
        except Exception:
            pass


# Global worker singleton
worker = MemoryWorker()
