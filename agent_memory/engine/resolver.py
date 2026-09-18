"""Conflict Resolution & Truth Maintenance Engine.
Detects contradictions between incoming facts and existing active memories,
marking outdated memories as superseded while preserving audit history.
"""

from typing import List, Tuple
from ..models.memory import Fact, MemoryRecord
from .embeddings import EmbeddingService


class ConflictResolver:
    """Resolves contradictions and updates state between new and old memories."""

    def __init__(self, embedding_service: EmbeddingService = None):
        self.embedding_service = embedding_service or EmbeddingService()

    def detect_conflicts(
        self, new_fact: Fact, existing_memories: List[MemoryRecord]
    ) -> List[Tuple[MemoryRecord, str]]:
        """
        Determines if a new fact contradicts or supersedes any existing active memories.
        
        Returns:
            List of (existing_memory_to_supersede, reason)
        """
        conflicts_to_supersede: List[Tuple[MemoryRecord, str]] = []

        for old_mem in existing_memories:
            if not old_mem.is_active:
                continue

            # Check 1: Entity + Attribute match with different values (Deterministic match)
            # e.g., entity="user", attribute="location", old="Chicago", new="Tokyo"
            if (
                new_fact.entity
                and new_fact.attribute
                and old_mem.entity.lower() == new_fact.entity.lower()
                and old_mem.attribute.lower() == new_fact.attribute.lower()
                and old_mem.value.lower() != new_fact.value.lower()
            ):
                reason = f"State update on {new_fact.entity}.{new_fact.attribute}: changed from '{old_mem.value}' to '{new_fact.value}'"
                conflicts_to_supersede.append((old_mem, reason))
                continue

            # Check 2: Semantic Opposition via Cosine Similarity on opposing statements
            # If the statements are talking about the exact same topic but with conflicting claims
            if old_mem.embedding and hasattr(new_fact, "embedding") and new_fact.embedding:
                similarity = self.embedding_service.cosine_similarity(old_mem.embedding, new_fact.embedding)
                # If two statements are very high in similarity (> 0.85) but have different words/values,
                # they are often contradictory variations of the same topic
                if similarity > 0.85 and old_mem.statement.lower() != new_fact.statement.lower():
                    reason = f"Semantic topic replacement (similarity={similarity:.2f})"
                    conflicts_to_supersede.append((old_mem, reason))

        return conflicts_to_supersede
